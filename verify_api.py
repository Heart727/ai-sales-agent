"""
一键自检脚本：不打开浏览器也能验证全部后端接口。

用法（先在一个终端里启动服务，再在另一个终端里跑本脚本）：
    python main.py          # 终端 1：启动服务（端口 8000）
    python verify_api.py    # 终端 2：跑自检

脚本按真实使用流程走一遍：
1. 权限检查：未登录访问线索接口必须被拒（401）
2. 注册（错误邀请码被拒 → 正确邀请码成功并自动登录）
3. 登录后的线索接口正常
4. 聊天流程（访客无需登录）：新建会话 → 发消息（带全 4 项信息）→
   AI 回复 + 自动生成线索 → 多轮记忆 → 手动结束
5. 登出后线索接口再次被拒（401）

每一步打印 PASS 或 FAIL，全部通过最后打印"✅ 全部通过"。
"""
import sys

import requests

# 服务的地址（本地启动时就是这个地址）
BASE = "http://127.0.0.1:8000"

# 测试用的注册邀请码（要和 .env 里的 AUTH_SIGNUP_CODE 一致）
SIGNUP_CODE = "dev-signup-2026"

passed = 0  # 通过的检查数
failed = 0  # 失败的检查数


def check(name: str, condition: bool, extra: str = ""):
    """记录一项检查结果：通过打印 PASS，失败打印 FAIL 并带上下文"""
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


# 两个"客户端"：
# - guest：访客，没登录（没有 cookie）
# - owner：老板，用 Session 保存登录 cookie
guest = requests.Session()
owner = requests.Session()

print("=" * 50)
print("AI 销售助手接口自检（含登录权限检查）")
print("=" * 50)

# ===== 1. 权限检查：未登录不能看线索 =====
print("\n[1] 未登录访问线索接口应被拒")
r = guest.get(f"{BASE}/api/leads", timeout=10)
check("GET /api/leads 返回 401", r.status_code == 401, f"实际 {r.status_code}")
r = guest.get(f"{BASE}/api/sessions", timeout=10)
check("GET /api/sessions 返回 401", r.status_code == 401, f"实际 {r.status_code}")
r = guest.delete(f"{BASE}/api/leads/1", timeout=10)
check("DELETE /api/leads/1 返回 401", r.status_code == 401, f"实际 {r.status_code}")

# ===== 2. 注册：邀请码错误被拒 =====
print("\n[2] 注册：错误邀请码被拒")
r = owner.post(f"{BASE}/api/auth/register", timeout=10, json={
    "username": "boss", "password": "secret123", "signup_code": "wrong-code",
})
check("返回 400", r.status_code == 400, f"实际 {r.status_code} {r.text[:100]}")

# ===== 3. 注册：正确邀请码成功（自动登录） =====
print("\n[3] 注册：正确邀请码成功")
r = owner.post(f"{BASE}/api/auth/register", timeout=10, json={
    "username": "boss", "password": "secret123", "signup_code": SIGNUP_CODE,
})
check("返回 200", r.status_code == 200, f"实际 {r.status_code} {r.text[:100]}")
check("cookie 里写入了令牌", "auth_token" in owner.cookies.get_dict(), "没有 cookie")

r = owner.get(f"{BASE}/api/auth/me", timeout=10)
check("已登录（/api/auth/me 返回 200）", r.status_code == 200 and r.json().get("username") == "boss")

# ===== 4. 重复注册同名用户被拒 =====
print("\n[4] 重复注册同名用户被拒")
r = owner.post(f"{BASE}/api/auth/register", timeout=10, json={
    "username": "boss", "password": "secret456", "signup_code": SIGNUP_CODE,
})
check("返回 400", r.status_code == 400, f"实际 {r.status_code}")

# ===== 5. 登录后的线索接口正常 =====
print("\n[5] 登录后线索接口正常")
r = owner.get(f"{BASE}/api/leads", timeout=10)
check("GET /api/leads 返回 200", r.status_code == 200, f"实际 {r.status_code}")
check("leads 是列表", isinstance(r.json().get("leads"), list))
r = owner.get(f"{BASE}/api/sessions", timeout=10)
check("GET /api/sessions 返回 200", r.status_code == 200, f"实际 {r.status_code}")

# ===== 6. 聊天流程（访客视角，无需登录） =====
print("\n[6] 聊天：新建会话 → 发消息 → AI 回复 + 自动生成线索")
r = guest.post(f"{BASE}/api/sessions", timeout=10)
check("新建会话返回 200", r.status_code == 200, f"实际 {r.status_code}")
sid = r.json().get("id")
check("拿到会话 id", isinstance(sid, int), f"实际 {r.json()}")
print(f"      会话 id = {sid}")

msg = "你好，我想做一个电商小程序，预算 3 万元，希望下个月上线，可以加我微信 test123 详聊"
r = guest.post(f"{BASE}/api/sessions/{sid}/messages", json={"content": msg}, timeout=120)
check("发消息返回 200", r.status_code == 200, f"实际 {r.status_code} {r.text[:200]}")
data = r.json()
check("AI 回复非空", bool(data.get("reply")), "reply 为空")
print(f"      AI 回复：{data.get('reply', '')[:80]}...")
lead = data.get("lead")
check("自动生成了线索卡片", lead is not None, "lead 为 None")
if lead:
    print(f"      线索卡片：需求={lead['requirement']} | 预算={lead['budget']} | "
          f"时间={lead['timeline']} | 联系={lead['contact']}")

# ===== 7. 多轮对话记忆 =====
print("\n[7] 多轮对话记忆")
r = guest.post(f"{BASE}/api/sessions/{sid}/messages",
               json={"content": "我刚才说的预算是多少？"}, timeout=120)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
reply2 = r.json().get("reply", "")
check("AI 记得预算 3 万", "3" in reply2, f"回复：{reply2[:100]}")

# ===== 8. 手动结束对话：已有卡片不重复生成 =====
print("\n[8] 手动结束对话")
r = guest.post(f"{BASE}/api/sessions/{sid}/end", timeout=120)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
same = r.json().get("lead")
check("返回的是同一张卡片", same and lead and same["id"] == lead["id"])

# ===== 9. 老板查看线索并删除 =====
print("\n[9] 老板查看并删除线索")
r = owner.get(f"{BASE}/api/leads", timeout=10)
leads = r.json().get("leads", [])
check("线索列表有 1 张卡片", len(leads) == 1, f"实际 {len(leads)} 张")
r = owner.delete(f"{BASE}/api/leads/{lead['id']}", timeout=10)
check("删除返回 200", r.status_code == 200, f"实际 {r.status_code}")
r = owner.get(f"{BASE}/api/leads", timeout=10)
check("删除后列表为空", len(r.json().get("leads", [])) == 0)

# ===== 10. 登出后再次被拒 =====
print("\n[10] 登出后线索接口再次被拒")
r = owner.post(f"{BASE}/api/auth/logout", timeout=10)
check("登出返回 200", r.status_code == 200, f"实际 {r.status_code}")
r = owner.get(f"{BASE}/api/leads", timeout=10)
check("登出后 GET /api/leads 返回 401", r.status_code == 401, f"实际 {r.status_code}")

# ===== 11. 错误场景 =====
print("\n[11] 错误场景")
r = guest.post(f"{BASE}/api/sessions/99999/messages", json={"content": "hi"}, timeout=10)
check("不存在的会话返回 404", r.status_code == 404, f"实际 {r.status_code}")
r = guest.post(f"{BASE}/api/sessions/{sid}/messages", json={"content": "   "}, timeout=10)
check("空消息返回 400", r.status_code == 400, f"实际 {r.status_code}")

# ===== 12. 限流实测：连发消息直到被 429 拦截 =====
# 前面的检查已经消耗了本分钟的部分配额（每 IP 每分钟 8 条），
# 这里继续连发空消息（空消息也会计配额，但不会调 AI、不花钱），
# 应该在几次之内收到 429。
# ⚠️ 注意：跑自检时请不要同时在浏览器里聊天，否则配额被聊天占用，这里数字会变。
print("\n[12] 限流实测：连发消息直到 429")
got_429 = False
detail_429 = ""
for i in range(12):
    r = guest.post(f"{BASE}/api/sessions/{sid}/messages", json={"content": "   "}, timeout=10)
    if r.status_code == 429:
        got_429 = True
        detail_429 = r.json().get("detail", "")
        retry_after = r.headers.get("Retry-After")
        check("响应带 Retry-After 头", retry_after is not None, "没有 Retry-After 头")
        break
check("收到 429 拦截", got_429, "连发 12 条都没被拦（如果刚才在聊天，请稍等一分钟后重跑）")
if got_429:
    print(f"      429 提示：{detail_429}")

# 总结
print("\n" + "=" * 50)
print(f"结果：{passed} 项通过，{failed} 项失败")
if failed == 0:
    print("✅ 全部通过")
else:
    print("❌ 有检查失败，请往上翻看 FAIL 项")
print("=" * 50)

# 有失败时退出码非 0（方便脚本化判断）
sys.exit(0 if failed == 0 else 1)
