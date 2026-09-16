"""
限流模块单元测试：直接测 rate_limit 的函数，不经过 HTTP、不调用 AI（零 API 费用）。

用法：
    python test_rate_limit.py

所有测试都使用保留的测试网段 IP（192.0.2.x，真实互联网上不存在），
不会和真实访客的计数互相干扰；测完自动清理产生的计数/封禁/会话数据。
"""
import sqlite3

import database as db
import rate_limit
import tempfile
from pathlib import Path
_test_directory = tempfile.TemporaryDirectory()
DB_PATH = str(Path(_test_directory.name) / "rate-test.db")
db.DB_PATH = DB_PATH
db.init_db()

# 测试专用 IP（RFC 5737 保留网段，永远不会是真实访客）
TEST_IP = "192.0.2.99"
TEST_IP2 = "192.0.2.100"

passed = 0
failed = 0


def check(name, condition, extra=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


def cleanup():
    """清掉本次测试产生的所有数据，保证可以反复跑"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM rate_limits WHERE key LIKE ?", (f"%{TEST_IP}%",))
    conn.execute("DELETE FROM rate_limits WHERE key LIKE ?", (f"%{TEST_IP2}%",))
    conn.execute("DELETE FROM rate_limits WHERE key LIKE 'global:msg:day%'")
    conn.execute("DELETE FROM bans WHERE ip IN (?, ?)", (TEST_IP, TEST_IP2))
    conn.commit()
    conn.close()


print("=" * 50)
print("限流模块单元测试（不调用 AI，零费用）")
print("=" * 50)
db.init_db()
cleanup()

# 1. 分钟限流：第 9 条消息应被拒
print("\n[1] 分钟限流：每 IP 每分钟上限")
rejected = False
reject_detail = ""  # 在 except 块里把提示存出来（Python 的 except 变量出块会被清除）
try:
    for i in range(9):
        rate_limit.check_message_rate(TEST_IP)
except rate_limit.RateLimited as e:
    rejected = True
    reject_detail = e.detail
    print(f"      第 9 次被拒，提示：{e.detail}，建议重试 {e.retry_after} 秒后")
check("第 9 条消息抛 RateLimited", rejected)
check("429 详情带中文提示", "稍后再试" in reject_detail)

# 2. 计数持久化：计数器写进了 SQLite（重启不丢，商用标准）
print("\n[2] 计数持久化到 SQLite")
conn = sqlite3.connect(DB_PATH)
row = conn.execute("SELECT count FROM rate_limits WHERE key = ?", (f"msg:min:{TEST_IP}",)).fetchone()
conn.close()
check("数据库里能查到计数", row is not None, "表里没有这条计数")
check("计数等于 9（含被拒那次）", row and row[0] == 9, f"实际 {row and row[0]}")

# 3. 窗口机制：同窗口累加，切换窗口后重置
print("\n[3] 窗口机制：同窗口累加，切换窗口后重置")
db.increment_rate(f"msg:min:{TEST_IP2}", "2026-08-19 10:00", 8)          # 窗口 10:00 第 1 次
_, count2 = db.increment_rate(f"msg:min:{TEST_IP2}", "2026-08-19 10:00", 8)  # 还是 10:00 窗口
check("同一窗口内计数累加（第2次=2）", count2 == 2, f"实际 {count2}")
_, count3 = db.increment_rate(f"msg:min:{TEST_IP2}", "2026-08-19 10:01", 8)  # 切到 10:01 窗口
check("窗口切换后重新计数（=1）", count3 == 1, f"实际 {count3}")

# 4. 日配额拦截与显式封禁
print("\n[4] 日配额拦截与显式封禁")
banned = False
try:
    for i in range(101):
        rate_limit.check_daily_message_quota(TEST_IP)
except rate_limit.RateLimited:
    banned = True
check("第 101 条抛 RateLimited", banned)
check("日额度耗尽不会自动封禁", db.get_ban(TEST_IP) is None)
rate_limit.auto_ban(TEST_IP, "手动测试封禁")
ban = db.get_ban(TEST_IP)
check("显式封禁已记录", ban is not None, "bans 表里没有记录")
check("封禁原因已记录（审计用）", ban and "封禁" in ban["reason"], f"实际 {ban and ban['reason']}")
try:
    rate_limit.check_ban(TEST_IP)
    check("封禁中再访问被拒", False)
except rate_limit.RateLimited as e:
    check("封禁中再访问被拒", True)
    check("提示带解封时间", "解除" in e.detail)

# 5. 建会话配额：第 21 个会话被拒
_original_creation = rate_limit.check_session_creation
def _daily_creation(ip):
    conn = db.get_conn()
    conn.execute("DELETE FROM rate_limits WHERE key=?", (f"session:min:{ip}",))
    conn.commit(); conn.close()
    return _original_creation(ip)
rate_limit.check_session_creation = _daily_creation
print("\n[5] 日建会话配额")
rejected = False
try:
    for i in range(21):
        rate_limit.check_session_creation(TEST_IP2)
except rate_limit.RateLimited:
    rejected = True
check("第 21 个会话抛 RateLimited", rejected)

# 6. 会话消息上限：60 条后拒绝
print("\n[6] 会话消息上限")
sid = db.create_session("限流测试会话")
conn = sqlite3.connect(DB_PATH)
for i in range(60):
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', 'x', datetime('now'))",
        (sid,),
    )
conn.commit()
conn.close()
rejected = False
try:
    rate_limit.check_session_message_cap(sid)
except rate_limit.RateLimited as e:
    rejected = True
    check("提示包含'新对话'引导", "新对话" in e.detail)
check("第 61 条消息被拒", rejected)
# 清理测试会话
conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
conn.commit()
conn.close()

# 7. 封禁过期自动解除
print("\n[7] 封禁过期自动解除")
from datetime import datetime, timedelta
past = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
db.ban_ip(TEST_IP2, "过期测试", past)
check("过期封禁记录被自动清除", db.get_ban(TEST_IP2) is None)
try:
    rate_limit.check_ban(TEST_IP2)
    check("过期封禁不拦请求", True)
except rate_limit.RateLimited:
    check("过期封禁不拦请求", False)

# 8. XFF 防伪造：未开 TRUST_PROXY 时伪造的 X-Forwarded-For 无效
print("\n[8] XFF 头防伪造（TRUST_PROXY=False 时）")
class FakeClient:
    host = "1.2.3.4"  # 真实 TCP 连接 IP
class FakeRequest:
    def __init__(self, headers): self.headers = headers; self.client = FakeClient()
ip = rate_limit.get_client_ip(FakeRequest({"x-forwarded-for": "9.9.9.9, 8.8.8.8"}))
check("伪造 XFF 被忽略，取真实连接 IP", ip == "1.2.3.4", f"实际取到 {ip}")

# 收尾：清理测试数据
cleanup()

print("\n" + "=" * 50)
print(f"结果：{passed} 项通过，{failed} 项失败")
print("✅ 全部通过" if failed == 0 else "❌ 有检查失败")
print("=" * 50)
exit(0 if failed == 0 else 1)
