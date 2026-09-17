# Vercel + Turso 面试展示部署设计

## 目标

把现有 AI 销售助手部署成一个可长期发给面试官访问的公开演示版本。访客可以免登录聊天，管理员通过登录页查看线索卡片；会话、消息、用户、限流计数和 AI 预算都必须保存在远程持久化数据库中。

## 约束

- 保留 FastAPI、原生 HTML/CSS/JS、DeepSeek OpenAI 兼容接口和现有 API。
- 本地开发继续支持项目目录中的 SQLite 文件，现有测试不需要联网或调用真实 AI。
- Vercel 部署使用无状态 Python Function，不能依赖本地文件作为业务数据层。
- Turso 凭证只存在服务端环境变量 `TURSO_DATABASE_URL` 和 `TURSO_AUTH_TOKEN`，不进入浏览器、Git 或示例输出。
- 访客会话归属、管理员认证、限流、AI 并发与每日预算策略保持现有行为。
- 聊天请求只调用一次模型生成回复；线索提取在访客点击“结束对话”时执行，避免 Serverless 请求连续等待两次模型调用。
- 公开展示仅用于作品集演示，不把真实客户个人信息放入演示数据库。

## 架构

Vercel 负责公开 HTTPS 地址、静态页面和 FastAPI Function。项目新增 `app.py` 作为 Vercel 识别入口，复用现有 `main:app`，不拆分前后端，也不改变浏览器请求路径。

`database.py` 保留现有数据库函数接口，只在 `get_conn()` 内选择连接驱动：本地没有 Turso 凭证时使用标准 `sqlite3`；同时提供两项 Turso 凭证时使用官方 `turso_serverless` 远程 DB-API 驱动。两项凭证只提供一项时立即抛出配置错误，避免线上静默退回临时本地文件。

启动时仍运行幂等 `init_db()`，通过远程连接创建表和索引。所有写操作继续使用短事务，不在 DeepSeek 网络调用期间持有数据库写锁。

## 部署配置

- `requirements.txt` 锁定 `turso_serverless==0.1.0`。
- `vercel.json` 为 `app.py` 配置 60 秒 Function 最大时长，与现有 DeepSeek 单次 45 秒超时相匹配。
- `.env.example` 增加 Turso 配置和线上 Cookie/CORS 来源设置说明。
- README 增加 Turso 创建数据库、取得 URL/token、Vercel 导入 GitHub、配置环境变量、部署后验证步骤。
- 只提交部署模板和文档，不提交 `.env`、API key、本地数据库或备份。

## 错误处理

- 缺少任一 Turso 凭证时拒绝启动远程模式并说明缺少配置。
- 远程数据库连接错误沿用现有 API 的错误边界，不把数据库内部凭证或上游异常返回给访客。
- Turso 未配置时本地行为保持不变，现有自动化测试继续用临时 SQLite 文件。

## 验证

- 先写一个连接选择测试并确认它在实现前失败。
- 实现后运行远程连接选择、部分凭证拒绝、现有 25 个安全/API 测试和 18 个限流检查。
- 用一个内存 fake 连接验证 `init_db()` 使用的 SQL 入口不依赖本地文件。
- 做 Python 编译、Vercel 配置 JSON 解析、Git 敏感文件检查。
- 不在自动测试中调用真实 Turso 或 DeepSeek；上线后由用户配置真实凭证，再按 README 做一次线上冒烟测试。
