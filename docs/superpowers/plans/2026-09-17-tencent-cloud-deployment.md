# 腾讯云单机部署准备实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 准备一套不暴露应用端口、支持 HTTPS 反向代理、systemd 托管和数据库备份的 Ubuntu 部署文件。

**Architecture:** FastAPI/Uvicorn 只监听 `127.0.0.1:8000`；Nginx 对外提供 HTTP/HTTPS，并覆盖代理头、请求体和超时；SQLite 放在独立数据目录，systemd 用非 root 用户运行。HTTPS 证书和域名绑定由服务器上实际域名决定，因此不在仓库内自动申请。

**Tech Stack:** Ubuntu 22.04 LTS、Python venv、Uvicorn、systemd、Nginx、Certbot、SQLite。

**Spec:** `README.md` 的“公网部署边界”。

## Global Constraints

- 应用端口只监听 `127.0.0.1:8000`，防火墙不开放 8000。
- 公网 HTTPS 部署必须设置 `COOKIE_SECURE=true` 和完整的 `PUBLIC_ORIGIN`。
- 只在显式配置可信代理网段时启用 `TRUST_PROXY=true`。
- 数据库升级只允许增量迁移，部署前必须备份。
- `.env`、数据库、备份和日志不能提交到 Git。

---

### Task 1: 服务器进程配置

**Files:**
- Create: `deploy/ai-sales-agent.service`

- [ ] systemd 服务使用固定应用用户、项目目录和 Uvicorn 的本机监听命令。
- [ ] 服务设置重启策略、环境文件路径和合理的打开文件数。
- [ ] 用 `systemd-analyze verify` 检查单元文件语法。

### Task 2: Nginx 代理配置

**Files:**
- Create: `deploy/nginx.conf`

- [ ] 代理到 `127.0.0.1:8000`，覆盖 `X-Forwarded-For`，避免信任外部伪造头。
- [ ] 设置 `client_max_body_size`、连接超时和 WebSocket/HTTP 连接头。
- [ ] 先提供 HTTP 配置；证书签发后再将 `server_name` 和 HTTPS 路径替换为真实域名。

### Task 3: 数据库备份脚本

**Files:**
- Create: `deploy/backup.sh`

- [ ] 使用 SQLite 在线 backup API，避免复制正在写入的数据库。
- [ ] 备份写入 `/var/backups/ai-sales-agent`，保留 14 天。
- [ ] 备份失败返回非零状态，供 systemd timer/监控发现。

### Task 4: 文档和验证

**Files:**
- Modify: `README.md`

- [ ] 写清服务器安装顺序、环境变量、Nginx/HTTPS 和防火墙要求。
- [ ] 说明部署需要域名和 SSH 凭据，当前配置不自动执行远程操作。
- [ ] 运行 Python 安全测试、前端语法检查、Git diff 检查。

