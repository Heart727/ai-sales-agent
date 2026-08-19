# 项目：AI 销售助手 MVP（作品集项目）

这是给 Claude Code 看的项目说明。

## 给谁用、解决什么问题

小商家/自由职业者挂在官网或落地页的 AI 销售接待员。访客进站后 AI 负责第一轮对话——了解客户需求、预算、时间、联系方式，结束后自动整理成"线索卡片"存进数据库。老板打开线索页就能看到今天来了哪些潜在客户，不用一条条翻聊天记录。

## 功能需求

1. 网页聊天界面：访客发消息、AI 回复；AI 扮演销售助手，主动询问 需求/预算/时间/联系方式 4 个关键问题
2. 多轮对话记忆：每个会话存 SQLite；AI 每次回复都带上该会话全部历史
3. 线索卡片：对话结束后 AI 把 4 项关键信息整理成卡片存入数据库并展示
   - AI 每轮回复后自动判断：4 项集齐 → 自动生成卡片（一个会话只生成一张）
   - 「结束对话」按钮兜底：信息不齐也生成，缺的字段标"未提供"
4. DeepSeek API（OpenAI 兼容接口，base_url=https://api.deepseek.com/v1，模型 deepseek-v4-pro，key 从 .env 读取）
5. 界面简洁中文、移动端可用；线索在独立页面 /leads 展示
6. 登录系统：访客聊天无需登录；/leads 和线索接口需登录（注册要邀请码 AUTH_SIGNUP_CODE，密码加盐哈希存库，登录状态存 cookie 令牌）；访客历史会话只存自己浏览器（localStorage）

## 技术栈

- 后端：Python + FastAPI + uvicorn
- 数据库：SQLite（Python 自带 sqlite3 模块，无 ORM）
- AI：openai 官方 SDK 指向 DeepSeek（base_url 配置在 .env）
- 前端：原生 HTML/CSS/JS（static/ 目录）
- 依赖：requirements.txt，虚拟环境 .venv/

## 文件结构

```
ai-sales-agent/
├── main.py          # FastAPI 入口 + 全部 API 路由（含登录接口和权限保护）
├── database.py      # 数据库层：建表、增删改查（其他模块不直接写 SQL）
├── ai.py            # AI 逻辑：生成回复 + 判断/提取线索 JSON
├── auth.py          # 认证逻辑：密码加盐哈希、令牌生成、邀请码校验
├── config.py        # 读 .env 配置（API key、模型、数据库路径、邀请码）
├── verify_api.py    # 一键自检脚本：不启动浏览器也能验证所有接口
├── requirements.txt
├── README.md        # 怎么配 API key、怎么运行
├── .env.example     # 配置模板（复制成 .env 后填真实值）
└── static/
    ├── index.html   # 聊天页（/）
    ├── leads.html   # 线索管理页（/leads，需登录）
    ├── login.html   # 登录/注册页（/login）
    ├── style.css    # 共享样式
    ├── app.js       # 聊天页逻辑（历史会话存 localStorage）
    ├── leads.js     # 线索页逻辑（未登录跳 /login）
    └── login.js     # 登录/注册逻辑
```

## 数据库设计（五张表）

- sessions：会话（id、标题、创建时间）
- messages：消息（id、所属会话、角色 user/assistant、内容、时间）
- leads：线索卡片（id、所属会话、需求、预算、时间、联系方式、摘要、时间）
- users：用户（id、用户名、密码哈希、盐、时间）——不存明文密码
- tokens：登录令牌（token、所属用户、时间）

## 开发约定

- 访客聊天完全开放；线索页/线索接口/会话列表接口需登录（注册要邀请码）
- 代码面向编程小白，关键处有详尽中文注释
- 错误处理不静默失败：AI 调用失败要提示用户；JSON 解析失败要打日志
- 每完成一个功能就运行验证，验证通过再进下一个
