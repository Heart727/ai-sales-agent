"""
一键自检脚本：不打开浏览器也能验证全部后端接口。

用法（先在一个终端里启动服务，再在另一个终端里跑本脚本）：
    python main.py          # 终端 1：启动服务（端口 8000）
    python verify_api.py    # 终端 2：跑自检

脚本会按真实使用流程走一遍：新建会话 → 发消息（带全 4 项信息）→
检查 AI 回复和自动生成的线索卡片 → 手动结束接口 → 线索列表 → 删除线索。
每一步打印 PASS 或 FAIL，全部通过最后打印"✅ 全部通过"。
"""
import sys

import requests

# 服务的地址（本地启动时就是这个地址）
BASE = "http://127.0.0.1:8000"

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


print("=" * 50)
print("AI 销售助手接口自检（每步都在打真实接口）")
print("=" * 50)

# 1. 会话列表初始应为空列表
print("\n[1] 会话列表（初始）")
r = requests.get(f"{BASE}/api/sessions", timeout=10)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
check("sessions 是列表", isinstance(r.json().get("sessions"), list))

# 2. 新建会话
print("\n[2] 新建会话")
r = requests.post(f"{BASE}/api/sessions", timeout=10)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
sid = r.json().get("id")
check("拿到会话 id", isinstance(sid, int), f"实际 {r.json()}")
print(f"      会话 id = {sid}")

# 3. 发消息：一条消息带全 4 项信息，应该同时拿到 AI 回复 + 自动生成的线索卡片
print("\n[3] 发消息（一条消息带全需求/预算/时间/联系方式）")
msg = "你好，我想做一个电商小程序，预算 3 万元，希望下个月上线，可以加我微信 test123 详聊"
r = requests.post(f"{BASE}/api/sessions/{sid}/messages", json={"content": msg}, timeout=120)
check("返回 200", r.status_code == 200, f"实际 {r.status_code} {r.text[:200]}")
data = r.json()
check("AI 回复非空", bool(data.get("reply")), "reply 为空")
print(f"      AI 回复：{data.get('reply', '')[:80]}...")
lead = data.get("lead")
check("自动生成了线索卡片", lead is not None, "lead 为 None")
if lead:
    print(f"      线索卡片：需求={lead['requirement']} | 预算={lead['budget']} | "
          f"时间={lead['timeline']} | 联系={lead['contact']}")

# 4. 会话消息列表：应该有 2 条（访客 1 条 + AI 1 条）
print("\n[4] 会话消息列表")
r = requests.get(f"{BASE}/api/sessions/{sid}/messages", timeout=10)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
msgs = r.json().get("messages", [])
check("有 2 条消息", len(msgs) == 2, f"实际 {len(msgs)} 条")
check("角色正确（user + assistant）", [m["role"] for m in msgs] == ["user", "assistant"],
      f"实际 {[m['role'] for m in msgs]}")

# 5. 多轮记忆：追问上一轮说过的事，AI 应记得
print("\n[5] 多轮对话记忆")
r = requests.post(f"{BASE}/api/sessions/{sid}/messages",
                  json={"content": "我刚才说的预算是多少？"}, timeout=120)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
reply2 = r.json().get("reply", "")
check("AI 记得预算 3 万", "3" in reply2, f"回复：{reply2[:100]}")
check("不会重复生成第二张卡片", r.json().get("lead") is not None and lead is not None)

# 6. 手动结束接口：已有卡片时直接返回现有卡片，不重复生成
print("\n[6] 手动结束对话")
r = requests.post(f"{BASE}/api/sessions/{sid}/end", timeout=120)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
same = r.json().get("lead")
check("返回的是同一张卡片", same and lead and same["id"] == lead["id"])

# 7. 线索列表：应有 1 张卡片
print("\n[7] 线索列表")
r = requests.get(f"{BASE}/api/leads", timeout=10)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
leads = r.json().get("leads", [])
check("有 1 张线索卡片", len(leads) == 1, f"实际 {len(leads)} 张")

# 8. 删除线索
print("\n[8] 删除线索")
r = requests.delete(f"{BASE}/api/leads/{lead['id']}", timeout=10)
check("返回 200", r.status_code == 200, f"实际 {r.status_code}")
r = requests.get(f"{BASE}/api/leads", timeout=10)
check("删除后列表为空", len(r.json().get("leads", [])) == 0)

# 9. 错误场景：不存在的会话
print("\n[9] 错误场景")
r = requests.post(f"{BASE}/api/sessions/99999/messages", json={"content": "hi"}, timeout=10)
check("不存在的会话返回 404", r.status_code == 404, f"实际 {r.status_code}")
r = requests.post(f"{BASE}/api/sessions/{sid}/messages", json={"content": "   "}, timeout=10)
check("空消息返回 400", r.status_code == 400, f"实际 {r.status_code}")

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
