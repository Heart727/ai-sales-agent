# 项目约定

FastAPI + SQLite + 原生前端，DeepSeek API。访客免登录聊天，邀请码注册的员工可管理同一商家的全部线索，不是多租户应用。

- 访客会话必须验证 HttpOnly cookie 归属；localStorage 只用于展示，不代表权限。
- 数据库修改必须保留旧数据，禁止删除业务库来测试或解封。
- 自动测试用临时数据库与模拟 AI；`python -X utf8 verify_api.py`。
- 模型调用统一经过 security.completion 的持久化预算和并发保护。
- 登录、注册、结束对话、新建会话也属于防刷范围。
- 公网需要 HTTPS、网关限流、可信代理白名单、备份监控；不能仅凭应用层测试就声称达到完整商用安全。
- Vercel 线上同时配置 `TURSO_DATABASE_URL` 与 `TURSO_AUTH_TOKEN` 使用远程 Turso；两项都为空才使用本地 SQLite，线上不能依赖本地数据库文件。
- 密钥只在环境变量/.env，不输出、不提交。
- 具体运行、配置及安全边界见 README.md。
