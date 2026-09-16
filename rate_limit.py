"""Persistent request quotas and explicit bans.
Quota exhaustion returns 429; reaching a quota alone never automatically bans an IP.
Forwarded headers are accepted only from explicitly allowlisted proxy peers.
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
    from ipaddress import ip_address, ip_network
    from config import TRUSTED_PROXY_IPS
    peer = request.client.host if request.client else "unknown"
    def trusted(value):
        try:
            return any(ip_address(value) in ip_network(net.strip()) for net in TRUSTED_PROXY_IPS if net.strip())
        except ValueError:
            return False
    if TRUST_PROXY and trusted(peer):
        chain = request.headers.get("x-forwarded-for", "").split(",")
        for value in reversed(chain):
            value = value.strip()
            try:
                value = str(ip_address(value))
            except ValueError:
                return peer
            if not trusted(value):
                return value
    return peer



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
    # Exhausting an allowance is not proof of abuse (shared NAT / retrying clients).
    _check_counter(f"msg:day:{ip}", _window("msg:day", ip), RATE_MSG_PER_DAY,
                   "今日消息额度已用完，请明日再试", 3600)


def check_session_creation(ip: str) -> None:
    _check_counter(f"session:min:{ip}", _window("msg:min", ip), 5,
                   "创建会话过于频繁", 60)
    _check_counter(f"session:day:{ip}", _window("msg:day", ip), RATE_SESSIONS_PER_DAY,
                   "今日会话数量已达上限", 3600)
    _check_counter("global:session:day", _window("msg:day", ip), 1000,
                   "今日会话额度已用完", 3600)


def check_global_quota(ip: str) -> None:
    # Exhaustion is a service-wide condition, not evidence against this visitor.
    _check_counter("global:msg:day", _window("msg:day", "global"),
                   RATE_GLOBAL_MSG_PER_DAY, "今日服务额度已用完，请稍后再试", 3600)


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


def check_auth_rate(ip, username):
    import hashlib
    account = hashlib.sha256(username.strip().casefold().encode()).hexdigest()
    _check_counter(f"auth:ip:{ip}", _window("msg:min",ip), 10, "登录尝试过于频繁", 60)
    _check_counter(f"auth:user:{account}", _window("msg:min",ip), 10, "登录尝试过于频繁", 60)
