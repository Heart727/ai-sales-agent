"""
防刷限流模块：在 AI 调用之前拦住恶意流量，保护 API 余额和数据库。

攻击者怎么薅我们（威胁模型）：
1. 写脚本对聊天接口狂发消息 → 每次消息都消耗 DeepSeek API 费用
2. 不停新建会话 → 绕过单会话上限 + 把数据库撑爆
3. 伪造 X-Forwarded-For 头 → 想骗过按 IP 计数（每换个假 IP 就重新计数）
4. 用很多台机器/代理 IP 同时刷 → 单 IP 限制拦不住，需要全局兜底

四道防线（商用标准）：
1. 分钟限流：每 IP 每分钟最多 N 条消息（拦突发脚本）
2. 日配额：每 IP 每天最多 N 条消息、N 个会话（拦慢速刷）
3. 会话上限：每个会话最多 N 条消息（拦单会话无限聊）
4. 全局兜底：全服务每天最多 N 条消息（拦分布式攻击）

超限的后果：
- 分钟限流超 → 返回 429（"发送太快"），不封禁（正常人连点太快不该被封）
- 日配额超 → 自动封禁该 IP 24 小时（商用 WAF 的 auto-ban 做法）
- 会话上限超 → 该会话不能再发消息，提示开新对话

所有计数存 SQLite（rate_limits/bans 表）而不是内存：
服务重启后计数不丢，攻击者无法靠"把服务搞重启"来绕过。
"""
from datetime import datetime, timedelta

from fastapi import Request

import database as db
from config import (
    BAN_HOURS,
    RATE_GLOBAL_MSG_PER_DAY,
    RATE_MSG_PER_DAY,
    RATE_MSG_PER_MINUTE,
    RATE_MSG_PER_SESSION,
    RATE_SESSIONS_PER_DAY,
    TRUST_PROXY,
)


class RateLimited(Exception):
    """
    自定义异常：表示请求被限流拒绝。
    带上 retry_after（建议多久后重试的秒数），main.py 统一转成
    HTTP 429 + Retry-After 响应头（HTTP 标准做法，客户端可据此自动重试）。
    """

    def __init__(self, detail: str, retry_after: int = 60):
        super().__init__(detail)
        self.detail = detail
        self.retry_after = retry_after


def get_client_ip(request: Request) -> str:
    """
    取请求的真实来源 IP。

    防伪造：只有明确配置了 TRUST_PROXY=True（表示部署在可信的反向代理后面）
    才读 X-Forwarded-For 头，且只取链上第一个 IP（代理追加的真实来源）。
    直连部署时攻击者随手伪造 XFF 头是无效的——我们直接用 TCP 连接 IP。
    """
    if TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _window(prefix: str, ip: str) -> str:
    """窗口起点字符串，如 "2026-08-19 10:30"（分钟窗口）/ "2026-08-19"（天窗口）"""
    now = datetime.now()
    if prefix == "msg:min":
        return now.strftime("%Y-%m-%d %H:%M")
    return now.strftime("%Y-%m-%d")


def _check_counter(key: str, window_start: str, limit: int, detail: str, retry_after: int) -> None:
    """计数 +1 并检查是否超限，超限抛 RateLimited"""
    over, count = db.increment_rate(key, window_start, limit)
    if over:
        raise RateLimited(detail, retry_after)


def check_ban(ip: str) -> None:
    """检查 IP 是否在封禁期，是则拒绝（附上解封时间）"""
    ban = db.get_ban(ip)
    if ban:
        raise RateLimited(
            f"访问过于频繁，已被临时限制，{ban['banned_until']} 后解除",
            retry_after=3600,
        )


def auto_ban(ip: str, reason: str) -> None:
    """自动封禁 IP（商用 WAF 的 auto-ban：日配额超限时调用）"""
    until = (datetime.now() + timedelta(hours=BAN_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    db.ban_ip(ip, reason, until)
    # 封禁事件必须留日志，商用系统靠它审计和追查攻击
    print(f"[限流] 已封禁 IP {ip}（{reason}），封到 {until}")


# ===== 四个对外检查函数：main.py 在对应接口入口处调用 =====

def check_message_rate(ip: str) -> None:
    """防线 1：每 IP 每分钟消息数（拦突发脚本），超限 429 但不封禁"""
    _check_counter(
        f"msg:min:{ip}", _window("msg:min", ip), RATE_MSG_PER_MINUTE,
        "发送太快了，请稍后再试", 60,
    )


def check_daily_message_quota(ip: str) -> None:
    """防线 2a：每 IP 每天消息总数（拦慢速刷），超限自动封禁"""
    try:
        _check_counter(
            f"msg:day:{ip}", _window("msg:day", ip), RATE_MSG_PER_DAY,
            "今日消息次数已达上限", 24 * 3600,
        )
    except RateLimited as e:
        auto_ban(ip, "日消息配额超限")
        raise e


def check_session_creation(ip: str) -> None:
    """防线 2b：每 IP 每天新建会话数，超限自动封禁"""
    try:
        _check_counter(
            f"session:day:{ip}", _window("msg:day", ip), RATE_SESSIONS_PER_DAY,
            "今日会话数量已达上限，请明天再来", 24 * 3600,
        )
    except RateLimited as e:
        auto_ban(ip, "日建会话配额超限")
        raise e


def check_global_quota(ip: str) -> None:
    """防线 4：全服务每天总消息数（拦分布式多 IP 攻击），超限封触发者"""
    try:
        _check_counter(
            "global:msg:day", _window("msg:day", "global"), RATE_GLOBAL_MSG_PER_DAY,
            "今日服务繁忙，请明天再来", 24 * 3600,
        )
    except RateLimited as e:
        auto_ban(ip, "触发全局配额")  # 全局打爆时，把触发这个请求的 IP 也封掉
        raise e


def check_session_message_cap(session_id: int) -> None:
    """
    防线 3：每个会话的消息总数上限。
    这条是查数据库（messages 表），不是计数器——发一条存一条。
    超限后拒绝继续发消息（不封 IP，提示开新对话即可）。
    """
    count = len(db.get_messages(session_id))
    if count >= RATE_MSG_PER_SESSION:
        raise RateLimited(
            "这个会话的消息已达上限，请点击「新对话」继续咨询", 0
        )
