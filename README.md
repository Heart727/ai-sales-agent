# AI 销售助手 MVP

小商家/自由职业者挂在官网或落地页的 AI 销售接待员。访客进站后 AI 负责第一轮对话——了解客户需求、预算、时间、联系方式，聊完自动整理成"线索卡片"存进数据库。老板打开线索页就能看到今天来了哪些潜在客户，不用一条条翻聊天记录。

## 功能

- 💬 **网页聊天**：访客发消息，AI 实时回复；AI 主动询问 需求/预算/时间/联系方式 4 个关键问题
- 🧠 **多轮对话记忆**：每个会话完整存进 SQLite，AI 每次回复都带上之前的所有对话
- 📇 **线索卡片**：4 项信息集齐后 AI **自动**生成线索卡片；也可以点「结束对话」按钮手动生成（信息不齐时缺的字段标"未提供"）
- 📱 **移动端可用**：简洁中文界面，手机宽度下正常使用
- 🗂️ **线索管理页** `/leads`：查看、删除所有线索

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | Python + FastAPI | 定义全部 API |
| 数据库 | SQLite | Python 自带 sqlite3，零配置 |
| AI | DeepSeek API | OpenAI 兼容接口，用 openai 官方 SDK 调用 |
| 前端 | 原生 HTML/CSS/JS | 无框架，简单直接 |

## 项目结构

```
ai-sales-agent/
├── main.py          # FastAPI 入口 + 全部 API 路由
├── database.py      # 数据库层：建表、增删改查
├── ai.py            # AI 逻辑：生成回复 + 提取线索 JSON
├── config.py        # 读 .env 配置
├── verify_api.py    # 一键自检脚本
├── static/          # 前端页面（index.html 聊天页 / leads.html 线索页）
├── requirements.txt # 依赖清单
└── .env.example     # 配置模板
```

## 本地运行

### 1. 准备环境（第一次需要）

```powershell
# 进入项目目录
cd ai-sales-agent

# 创建虚拟环境（隔离项目依赖，不污染系统 Python）
python -m venv .venv

# 激活虚拟环境（Windows PowerShell）
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

> SQLite 是 Python 自带的，不用装；前端是原生 HTML，也不用装。

### 2. 配置 API Key

1. 复制配置模板：把 `.env.example` 复制一份，改名为 `.env`
2. 打开 `.env`，填入你的 DeepSeek API Key（在 https://platform.deepseek.com 注册后获取）：

```env
DEEPSEEK_API_KEY=你的-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
```

> ⚠️ 模型名不要用 `deepseek-chat`——旧别名不会报错，但会被静默映射到弱模型，回答质量悄悄变差。
> ⚠️ `.env` 里是密钥，已被 .gitignore 排除，不会上传到 GitHub。

### 3. 启动

```powershell
python main.py
```

看到 `Uvicorn running on http://0.0.0.0:8000` 就成功了。打开浏览器访问：

- 聊天页：http://127.0.0.1:8000/
- 线索管理页：http://127.0.0.1:8000/leads

## 测试方法

### 方式一：一键自检（推荐，30 秒）

另开一个终端（保持服务运行），跑：

```powershell
python verify_api.py
```

它会按真实流程打一遍全部接口：建会话 → 发消息（带全 4 项信息）→ 检查 AI 回复和**自动生成**的线索 → 多轮记忆 → 手动结束 → 删除线索 → 错误场景。全部 `PASS` 且最后显示 `✅ 全部通过` 即后端正常。

### 方式二：浏览器手动测试

1. 打开 http://127.0.0.1:8000/ ，页面会自动开始一个新对话
2. 和 AI 聊天，试着先报预算、后报需求，最后问一句"我刚才说的预算是多少？"——AI 记得住，说明多轮记忆生效
3. 当你说完 需求/预算/时间/联系方式 后，聊天区会弹出绿色提示条"✅ 已生成线索卡片"
4. 打开 http://127.0.0.1:8000/leads ，能看到刚才生成的线索卡片，点「删除」可以删掉
5. 手机上测试：按 F12 打开开发者工具 → 切换设备模拟（或直接手机访问同一局域网 IP），验证窄屏布局

### 数据库长什么样

对话和线索都存在项目根目录的 `sales_agent.db`（自动生成）。可以用任意 SQLite 工具打开看三张表：`sessions`（会话）、`messages`（消息）、`leads`（线索卡片）。

## 部署到 Koyeb（免费，多数情况不绑卡）

**方式一：一键部署（推荐）**

点击下面的按钮，Koyeb 会自动填好仓库、启动命令、端口等所有配置：

[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&builder=buildpack&repository=github.com/Heart727/ai-sales-agent&branch=main&name=ai-sales-agent&run_command=uvicorn%20main:app%20--host%200.0.0.0%20--port%20%24PORT&ports=8000;http;/)

1. 用 GitHub 账号登录 Koyeb（https://app.koyeb.com），点击上面按钮进入创建页
2. 确认配置没问题，点页面底部的 **Create Service / Deploy**
3. 等构建完成（约 2~3 分钟），进服务 → **Settings → Environment variables**，添加 `DEEPSEEK_API_KEY`（复制 .env 里的值）→ Koyeb 会自动重新部署
4. 打开 `https://ai-sales-agent-你的用户名.koyeb.app` 即可使用

**方式二：手动创建**

1. https://app.koyeb.com 登录 → 点 **Create Service** → 部署方式选 **GitHub** → 选 `ai-sales-agent` 仓库、`main` 分支
2. Builder 保持 **Buildpack**；Run command 填 `uvicorn main:app --host 0.0.0.0 --port $PORT`；Ports 填 `8000`
3. 实例规格选最小的（免费额度内）→ Deploy
4. 部署后在 Settings → Environment variables 添加 `DEEPSEEK_API_KEY`，自动重新部署

> ⚠️ Koyeb 免费版注意点（演示够用）：
> - 免费版只给 1 个服务名额，实例 512MB 内存
> - 服务闲置约 1 小时后休眠，下次访问要等 30~60 秒"冷启动"
> - 免费版没有持久化磁盘：**重新部署时 SQLite 数据会被清空**（应用启动时自动重建空表，不影响使用，只是旧线索会消失）

## API 一览

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /api/sessions | 新建会话 |
| GET | /api/sessions | 会话列表（带"已生成线索"标记） |
| GET | /api/sessions/{id}/messages | 某会话的全部消息 |
| POST | /api/sessions/{id}/messages | 发消息 → 返回 AI 回复（可能同时生成线索） |
| POST | /api/sessions/{id}/end | 手动结束对话，强制生成线索 |
| GET | /api/leads | 线索列表 |
| DELETE | /api/leads/{id} | 删除线索 |
