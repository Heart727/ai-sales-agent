# Vercel + Turso 部署改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让现有 AI 销售助手可以在 Vercel 上运行，并使用 Turso 远程数据库持久化公开演示数据。

**Architecture:** 保留现有 FastAPI 路由和 `database.py` 公共函数接口。`get_conn()` 根据是否同时配置 `TURSO_DATABASE_URL` 与 `TURSO_AUTH_TOKEN` 选择本地 `sqlite3` 或官方 `turso_serverless` DB-API；新增 `app.py` 作为 Vercel 入口，线上请求仍由现有 FastAPI 应用处理。

**Tech Stack:** Python 3.12+、FastAPI、SQLite、Turso `turso_serverless==0.1.0`、Vercel Python Function、原生 HTML/CSS/JS、DeepSeek OpenAI-compatible API。

**Spec:** `docs/superpowers/specs/2026-09-17-vercel-turso-deployment-design.md`

## Global Constraints

- 本地开发继续使用 SQLite 文件，已有自动化测试不调用真实 AI 或真实 Turso。
- Vercel 线上业务数据必须使用 Turso 远程数据库，不能依赖临时本地文件。
- `TURSO_DATABASE_URL` 与 `TURSO_AUTH_TOKEN` 必须同时存在；只存在一项时拒绝建立连接。
- 访客会话归属、管理员认证、限流、AI 并发和每日预算行为保持不变；线索提取只在结束对话接口执行。
- 密钥只放环境变量，不写入 Git、不打印、不返回浏览器。

---

### Task 1: 数据库驱动选择

**Files:**
- Create: `test_database_backend.py`
- Modify: `database.py:12-27`
- Modify: `config.py:40-55`
- Modify: `requirements.txt:13-18`

**Interfaces:**
- `database.get_conn()` 在本地返回标准 SQLite 连接；远程模式调用 `turso_serverless.connect(url, auth_token=token)`。
- 远程连接必须设置 Turso 驱动自己的 `Row` 行工厂，以保留现有 `row["name"]` 和 `dict(row)` 用法。

- [ ] **Step 1: 写连接选择的失败测试**

```python
def test_get_conn_uses_turso_when_both_credentials_are_present():
    fake_connection = FakeConnection()
    with patch.object(config, "TURSO_DATABASE_URL", "turso://demo"), \
         patch.object(config, "TURSO_AUTH_TOKEN", "secret"), \
         patch("turso_serverless.connect", return_value=fake_connection) as connect:
        result = database.get_conn()

    connect.assert_called_once_with("turso://demo", auth_token="secret")
    assert result is fake_connection
    assert result.row_factory is turso_serverless.Row


def test_get_conn_rejects_partial_turso_credentials():
    with patch.object(config, "TURSO_DATABASE_URL", "turso://demo"), \
         patch.object(config, "TURSO_AUTH_TOKEN", ""):
        with pytest.raises(RuntimeError, match="TURSO_DATABASE_URL.*TURSO_AUTH_TOKEN"):
            database.get_conn()
```

`FakeConnection` 只需包含可赋值的 `row_factory` 字段；测试不得访问真实 Turso。

- [ ] **Step 2: 运行失败测试**

Run: `.venv\\Scripts\\python.exe -m unittest -v test_database_backend`

Expected: FAIL，因为 `database.get_conn()` 还只会调用本地 `sqlite3.connect()`，且配置模块没有 Turso 配置。

- [ ] **Step 3: 实现最小连接适配**

在 `config.py` 中读取并去除空白：

```python
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()
```

在 `database.py` 中保留 `DB_PATH` 变量以兼容现有测试，并实现：

```python
def get_conn():
    has_url = bool(config.TURSO_DATABASE_URL)
    has_token = bool(config.TURSO_AUTH_TOKEN)
    if has_url != has_token:
        raise RuntimeError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be configured together")
    if has_url:
        import turso_serverless
        conn = turso_serverless.connect(config.TURSO_DATABASE_URL, auth_token=config.TURSO_AUTH_TOKEN)
        conn.row_factory = turso_serverless.Row
        return conn
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn
```

把 `turso_serverless==0.1.0` 加入依赖清单。不要改数据库函数调用方，不要在连接适配中新增缓存或长连接。

- [ ] **Step 4: 运行连接测试和原有回归**

Run: `.venv\\Scripts\\python.exe -m unittest -v test_database_backend`

Expected: PASS，覆盖远程选择、行工厂和部分凭证拒绝。

Run: `.venv\\Scripts\\python.exe -X utf8 verify_api.py`

Expected: 25 个安全/API 测试和 18 个限流检查全部通过。

- [ ] **Step 5: 提交任务**

```powershell
git add config.py database.py requirements.txt test_database_backend.py
git commit -m "feat: support Turso remote database connections"
```

### Task 2: Vercel 入口与线上配置

**Files:**
- Create: `app.py`
- Create: `vercel.json`
- Modify: `.env.example`

**Interfaces:**
- Vercel 加载 `app:app`；`app.py` 只负责从 `main` 导出已存在的 FastAPI 实例。
- `vercel.json` 配置 `app.py` 的 Function 最大时长为 60 秒，不添加会改变 API 路径的重写规则。

- [ ] **Step 1: 写入口和配置失败测试**

```python
def test_vercel_entry_exports_fastapi_app():
    from fastapi import FastAPI
    from app import app
    assert isinstance(app, FastAPI)


def test_vercel_json_targets_app_with_sixty_second_limit():
    data = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    assert data["functions"]["app.py"]["maxDuration"] == 60
```

- [ ] **Step 2: 运行失败测试**

Run: `.venv\\Scripts\\python.exe -m unittest -v test_vercel_config`

Expected: FAIL，因为入口和 `vercel.json` 尚不存在。

- [ ] **Step 3: 写最小 Vercel 适配**

`app.py` 内容：

```python
from main import app

__all__ = ["app"]
```

`vercel.json` 内容：

```json
{
  "functions": {
    "app.py": {
      "maxDuration": 60
    }
  }
}
```

`.env.example` 增加线上变量：`TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`、`COOKIE_SECURE=true`、`PUBLIC_ORIGIN=https://你的-vercel-域名.vercel.app`。保留本地 `DATABASE_PATH` 注释示例。

- [ ] **Step 4: 运行配置测试和 Python 编译**

Run: `.venv\\Scripts\\python.exe -m unittest -v test_vercel_config`

Expected: PASS。

Run: `.venv\\Scripts\\python.exe -m py_compile app.py config.py database.py main.py`

Expected: exit code 0。

- [ ] **Step 5: 提交任务**

```powershell
git add app.py vercel.json .env.example test_vercel_config.py
git commit -m "feat: add Vercel FastAPI deployment entrypoint"
```

### Task 3: 部署文档和安全验收

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Create: `docs/superpowers/plans/2026-09-17-vercel-turso-deployment.md` (this plan)

- [ ] **Step 1: 写文档检查测试**

```python
def test_readme_has_vercel_turso_setup_steps():
    text = Path("README.md").read_text(encoding="utf-8")
    for marker in ("Vercel", "Turso", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "面试官"):
        assert marker in text
```

- [ ] **Step 2: 运行失败测试**

Run: `.venv\\Scripts\\python.exe -m unittest -v test_docs`

Expected: FAIL，因为 README 还没有 Turso/Vercel 操作步骤。

- [ ] **Step 3: 补全 README**

增加明确的操作顺序：创建 Turso 数据库和 token、GitHub 导入 Vercel、配置 DeepSeek/Turso/邀请码/Cookie 变量、部署后打开首页、注册管理员、访客聊天、管理员查看 `/leads`，并说明不要把真实客户信息放进面试演示。补充平台边界：Vercel Function 无常驻进程，持久数据必须在 Turso；免费方案适合作品集演示，不等于完整生产级 SLA。

增加环境变量表，明确 `PUBLIC_ORIGIN` 使用最终 Vercel 域名，`COOKIE_SECURE=true`，不要设置 `DATABASE_PATH` 作为线上业务库。

- [ ] **Step 4: 运行文档测试和完整验证**

Run: `.venv\\Scripts\\python.exe -m unittest -v test_docs`

Expected: PASS。

Run: `.venv\\Scripts\\python.exe -X utf8 verify_api.py`

Expected: 25 个安全/API 测试、18 个限流检查全部通过。

Run: `git diff --check`

Expected: no whitespace errors。

Run: `git status --short`

Expected: 只出现本任务源文件，不出现 `.env`、`*.db`、`.venv` 或密钥内容。

- [ ] **Step 5: 提交任务**

```powershell
git add README.md CLAUDE.md test_docs.py
git commit -m "docs: document Vercel and Turso deployment"
```

### Task 4: 最终验收

- [ ] **Step 1: 检查提交和敏感文件**

Run: `git log --oneline -5; git ls-files .env "*.db"`

Expected: `.env` 和数据库文件没有被 Git 跟踪。

- [ ] **Step 2: 运行全套自动检查**

Run: `.venv\\Scripts\\python.exe -X utf8 verify_api.py`

Expected: exit code 0，25 + 18 项检查通过，无真实 AI 请求。

Run: `.venv\\Scripts\\python.exe -m unittest -v test_database_backend test_vercel_config test_docs`

Expected: all new tests pass。

- [ ] **Step 3: 检查远程依赖已锁定**

Run: `Select-String -Path requirements.txt -Pattern "turso_serverless==0.1.0"`

Expected: exactly one matching dependency line。

- [ ] **Step 4: 记录本地交付结果**

输出 Git 分支、提交号、测试结果和用户需要在 Turso/Vercel 控制台手动填写的环境变量。不要声称已经完成真实线上部署，因为当前会话没有用户的 Turso/Vercel 凭证。
