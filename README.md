# AI 销售助手

面向小商家和自由职业者的第一轮销售接待：访客描述需求，AI 收集需求、预算、时间、联系方式，生成跟进线索。FastAPI + SQLite + 原生 HTML/CSS/JS，DeepSeek 使用 OpenAI 兼容接口。

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填写自己的 DEEPSEEK_API_KEY 和随机 AUTH_SIGNUP_CODE
.venv\Scripts\python.exe main.py
```

已有 `.env` 请直接编辑，不要覆盖。聊天：http://127.0.0.1:8000/；管理员登录：http://127.0.0.1:8000/login；线索：http://127.0.0.1:8000/leads。
注册仅限持有邀请码的员工，所有注册账号都能管理同一个商家的线索。不是多租户系统。邀请注册完成后可清空 `AUTH_SIGNUP_CODE` 并重启来关闭注册。

## 配置

- `DEEPSEEK_API_KEY`：仅保存在 .env/服务器环境变量，不交给浏览器。
- `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1`。
- `DEEPSEEK_MODEL`：使用你的 DeepSeek 账户实际支持的模型；不要把别名映射当作长期保证。
- `DATABASE_PATH`：SQLite 文件绝对路径；默认项目目录的 sales_agent.db。
- `COOKIE_SECURE=false`：仅本地 HTTP 调试；公网 HTTPS 必须 true。
- `PUBLIC_ORIGIN`：公网完整 HTTPS 来源，例如 https://sales.example.com，不带路径。
- `TRUST_PROXY=false`：默认忽略 XFF；Nginx 后使用 true 并显式配置 `TRUSTED_PROXY_IPS=127.0.0.1/32`。
- `AI_MAX_CONCURRENT=4`、`AI_DAILY_CALLS=500`、`AI_DAILY_UNITS=200000`：每次真正调用模型前通过 SQLite 原子预留。聊天和提取分别计费计数，超时/失败也不退还预留量。日界为 UTC。

`AI_DAILY_UNITS` 是 UTF-8 字节数、协议余量与最大输出 token 的保守合计，用于控制工作量，**不是精确 token 计费或人民币余额保证**。请同时在模型服务商账户配置消费限制及余额告警。SDK 自动重试已关闭，单次网络超时 45 秒。

## 已实现的保护

- 随机访客 cookie（HttpOnly）绑定会话；读、发消息、结束都验证归属，管理员仅可额外读取历史。改 URL 中的 ID 不会获得别人数据。
- 旧会话迁移后保留，但没有归属凭证，只对管理员开放；不会根据 localStorage 认领旧会话。
- 登录/注册：每 IP、每用户名每分钟各 10 次，登录 cookie 服务端也检查 30 天过期，登出撤销令牌并清 cookie。
- IP 消息限流/日配额、每日会话配额、单会话 60 条消息（包含双方），全局日请求上限；日配额或全局额度耗尽只返回 429，不自动封禁访客；显式封禁仍保留。
- 建会话每 IP 每分钟 5 次、全局每天 1000 次；空对话不能生成线索。
- 消息最多 2000 字符，累计输入历史最多 16000 字符（最终整理额外容纳最后一条最多 8000 字符的回复），请求体最多 32 KiB；每次回复仍携带完整历史，达到上限明确拒绝而不偷偷截断。
- 同一会话同时只接受一个写入请求；共享 SQLite 中的租约限制 AI 并发。异常退出租约最多 300 秒过期；网络调用如果异常持续超过租期，不能把它当成严格的物理进程隔离，生产网关还需超时控制。
- 跨站浏览器写请求被拒；错误响应不回传上游内部异常。已成功的回复不因提取失败而丢失，页面提示稍后重试整理。

## 验证

```powershell
.venv\Scripts\python.exe -X utf8 verify_api.py
```

默认使用临时数据库和模拟 AI，运行安全/API 回归及限流检查，无 API 费用，不需要启动服务，不会修改业务数据。覆盖跨访客越权、认证、并发、预算耗尽、错误释放、迁移保留数据等。

人工验证：
1. 无痕窗口聊天；另一独立浏览器访问该会话的 messages 接口，应为 404。
2. 报齐四项信息，管理员登录后查看线索；重复结束只返回同一张卡片。
3. 刷新页面恢复当前会话，不自动新建；等待回复期间不能重复发送或切换对话。
4. 登出后 /api/leads 为 401，登录/注册两个标签互斥显示。
5. 真正验证 DeepSeek：在本地聊天一次并检查回复、线索；此步骤会消耗你的 API 额度。

不要删除 sales_agent.db 来解封或运行测试。升级前请用 SQLite backup 或停机复制备份文件；启动时只做增量建表/加列迁移。

## 公网部署边界

代码提供应用层加固，**不等于完成生产部署或防住 DDoS**。本次没有部署任何云平台，也不保证平台免费或无需绑卡。

使用 Ubuntu + Nginx + HTTPS；应用只监听 127.0.0.1:8000，防火墙不要对公网开放 8000。用非 root 服务账号及 systemd 托管。启动命令：

```sh
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

必须关闭 Uvicorn 自己的代理头重写，来源 IP 由应用的显式可信代理白名单处理。Nginx 需覆盖而非盲目保留外部 XFF（单层代理示例 `proxy_set_header X-Forwarded-For $remote_addr;`），转发 Host，设置请求体、连接数、请求速率和超时上限。多层 CDN 按实际拓扑配置信任边界，不能直接信任任意 XFF。

上线还需：有效 TLS 证书、COOKIE_SECURE/PUBLIC_ORIGIN、云端 WAF/验证码接入（如有公网机器流量）、数据库备份和恢复演练、日志告警、数据保留与清理规则。SQLite 只适合单机共享本地磁盘部署；多台服务器应迁移数据库和分布式限流，不可每台各存一份配额。

## 文件

main.py 路由；database.py 数据与迁移；ai.py 模型调用；auth.py 认证；rate_limit.py 请求限流；security.py 归属/请求体/AI 预算；config.py 配置；static/ 页面；test_security.py 与 test_rate_limit.py 隔离测试。
