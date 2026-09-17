# AI 销售助手

面向小商家和自由职业者的第一轮销售接待：访客描述需求，AI 收集需求、预算、时间、联系方式，生成跟进线索。FastAPI + SQLite/Turso + 原生 HTML/CSS/JS，DeepSeek 使用 OpenAI 兼容接口。

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
- `TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`：公开部署时同时填写，应用会通过 `turso_serverless` 访问远程 Turso；只填一项会拒绝连接。本地开发两项都留空。
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

## 腾讯云 Ubuntu 部署准备

仓库内的 [`deploy/`](deploy/) 提供 systemd、Nginx 和 SQLite 备份模板。真正部署前需要一个域名解析到服务器公网 IP，以及 SSH 登录权限；本地环境不会自动连接或修改云服务器。

服务器上的推荐目录和顺序：

```sh
sudo adduser --system --group --home /opt/ai-sales-agent ai-sales
sudo mkdir -p /opt/ai-sales-agent /var/lib/ai-sales-agent /var/backups/ai-sales-agent
sudo chown -R ai-sales:ai-sales /opt/ai-sales-agent /var/lib/ai-sales-agent
git clone https://github.com/Heart727/ai-sales-agent.git /opt/ai-sales-agent
cd /opt/ai-sales-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo cp .env.example /etc/ai-sales-agent.env
sudo chmod 600 /etc/ai-sales-agent.env
```

编辑 `/etc/ai-sales-agent.env`：填写 API key 和随机邀请码，并取消注释 `DATABASE_PATH=/var/lib/ai-sales-agent/sales_agent.db`，让应用用户能写数据库。公网 HTTPS 后必须使用 `COOKIE_SECURE=true`、`PUBLIC_ORIGIN=https://你的域名`。如果 Nginx 在本机，配置 `TRUST_PROXY=true` 和 `TRUSTED_PROXY_IPS=127.0.0.1/32`，否则保持 false。

```sh
sudo cp deploy/ai-sales-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-sales-agent
sudo systemctl status ai-sales-agent
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ai-sales-agent
# 将 SERVER_NAME 替换为真实域名，再建立 sites-enabled 链接
sudo ln -s /etc/nginx/sites-available/ai-sales-agent /etc/nginx/sites-enabled/ai-sales-agent
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d 你的域名
sudo install -m 750 deploy/backup.sh /usr/local/sbin/ai-sales-agent-backup
```

腾讯云防火墙只放行 22、80、443；不要放行 8000。部署前后用 `backup.sh` 做一次 SQLite 备份和完整性检查，升级时先备份、再拉代码、再重启服务。公网上线前还要配置云端 WAF/验证码、日志告警、消费告警和恢复演练。

## 面试官公开演示：Vercel + Turso

没有云服务器时，推荐用 Vercel 发布页面和 FastAPI，用 Turso 保存会话、消息、用户、线索和限流数据。Vercel 的公开地址适合作品集和面试展示；线上不要设置 `DATABASE_PATH`，否则会退回本地文件，不能作为可靠的业务数据库。

### 1. 创建 Turso 数据库

先安装并登录 [Turso CLI](https://docs.turso.tech/cli/introduction)，然后执行：

```sh
turso auth login
turso db create ai-sales-agent
turso db show ai-sales-agent --url
turso db tokens create ai-sales-agent
```

保存命令输出的数据库 URL 和 token。它们只填写到 Vercel 环境变量，不要写入 `.env.example`、GitHub 或截图。

### 2. 导入 Vercel

1. 打开 [Vercel](https://vercel.com/)，用 GitHub 登录并导入 `Heart727/ai-sales-agent`。
2. Framework Preset 保持自动识别，Root Directory 使用仓库根目录，不需要配置 Build Command。
3. 在 Project Settings → Environment Variables 中为 Production 填写：

```text
DEEPSEEK_API_KEY=你的 DeepSeek key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
AUTH_SIGNUP_CODE=随机且难猜的邀请码
TURSO_DATABASE_URL=turso db show 输出的 URL
TURSO_AUTH_TOKEN=turso db tokens create 输出的 token
COOKIE_SECURE=true
PUBLIC_ORIGIN=https://你的项目名.vercel.app
```

不要在线上配置 `DATABASE_PATH`。`PUBLIC_ORIGIN` 必须是最终 Vercel 地址，不带路径；如果项目地址发生变化，记得同步修改它并重新部署。

### 3. 给面试官的验证路径

部署完成后依次验证：

1. 打开首页，访客无需登录即可新建会话并发送一条消息。
2. 刷新页面，确认当前会话仍能恢复；在另一浏览器打开同一个会话 ID 应不能读取消息。
3. 访问 `/login`，用 `AUTH_SIGNUP_CODE` 注册管理员账号。
4. 回到聊天页完成需求、预算、时间和联系方式，访问 `/leads` 查看线索卡片。
5. 退出登录后访问 `/api/leads` 应返回 401；再登录可以继续查看线索。

线上首次聊天会消耗 DeepSeek 额度。面试演示请使用虚构客户信息，不要录入真实姓名、电话、微信或邮箱；定期在 Turso 中清理演示线索。

Vercel Function 没有常驻进程，Turso 远程数据库是线上持久化边界。这个方案适合作品集演示和小规模面试访问，不等于完整生产部署；正式商用还需要平台账单上限、WAF、日志告警、备份恢复和数据保留策略。

## 文件

main.py 路由；database.py 数据与迁移；ai.py 模型调用；auth.py 认证；rate_limit.py 请求限流；security.py 归属/请求体/AI 预算；config.py 配置；static/ 页面；test_security.py 与 test_rate_limit.py 隔离测试。
