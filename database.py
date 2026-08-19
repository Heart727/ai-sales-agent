"""
数据库层：负责 SQLite 的所有操作（建表、增删改查）。

为什么单独一个文件？
让 main.py（接口层）和 ai.py（AI 层）不直接写 SQL，
所有数据库操作都走这里的函数——改表结构时只改这一个文件。

SQLite 是什么？
一个"文件型"数据库：整个数据库就是一个文件（sales_agent.db），
Python 自带 sqlite3 模块就能操作，不需要安装和启动任何数据库软件。
"""
import sqlite3
from datetime import datetime

from config import DB_PATH


def get_conn():
    """
    获取数据库连接（每次操作新建一个连接，用完关闭）。
    这是 SQLite 的简单用法：SQLite 是单文件数据库，新建连接的开销很小。
    """
    conn = sqlite3.connect(DB_PATH)
    # 关键设置：让查询结果支持"按列名取值"，例如 row["content"]
    # 不设置的话只能按位置取值 row[0]，代码可读性差
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    建三张表（如果表已经存在就不动，所以可以放心地每次启动都调用）。

    三张表的关系：
    - sessions（会话）：一个访客的一次对话，相当于"聊天窗口"
    - messages（消息）：属于某个会话的一句话，通过 session_id 关联
    - leads（线索卡片）：对话结束后生成的客户信息，通过 session_id 关联
    """
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,  -- 自增主键，每次新建自动 +1
                title      TEXT NOT NULL DEFAULT '新对话',      -- 会话标题（取第一句话的前 20 个字）
                created_at TEXT NOT NULL                        -- 创建时间（ISO 格式字符串）
            );

            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,                    -- 属于哪个会话（关联 sessions.id）
                role       TEXT NOT NULL,                       -- 角色：user（访客）/ assistant（AI）
                content    TEXT NOT NULL,                       -- 消息内容
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS leads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL UNIQUE,            -- 属于哪个会话（UNIQUE：一个会话只允许一张卡片）
                requirement TEXT NOT NULL,                      -- 需求：客户想要什么
                budget      TEXT NOT NULL,                      -- 预算：愿意花多少钱
                timeline    TEXT NOT NULL,                      -- 时间：什么时候要
                contact     TEXT NOT NULL,                      -- 联系方式：电话/微信/邮箱
                summary     TEXT NOT NULL,                      -- 跟进摘要：整段对话的一句话总结
                created_at  TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _now():
    """当前时间的 ISO 格式字符串，例如 2026-08-19 10:30:00"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================== 会话（sessions）相关操作 ====================

def create_session(title: str = "新对话") -> int:
    """新建一个会话，返回新会话的 id（数据库自增生成）"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO sessions (title, created_at) VALUES (?, ?)",
            (title, _now()),
        )
        conn.commit()
        return cur.lastrowid  # 刚插入那行的自增 id
    finally:
        conn.close()


def get_session(session_id: int) -> dict | None:
    """按 id 查会话，不存在返回 None（后面接口用这个判断"会话不存在"）"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_sessions() -> list[dict]:
    """列出所有会话，最新的在最前面"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_session_title(session_id: int, title: str) -> None:
    """更新会话标题（用于把第一句话的前 20 个字存成标题）"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE sessions SET title = ? WHERE id = ?", (title, session_id)
        )
        conn.commit()
    finally:
        conn.close()


# ==================== 消息（messages）相关操作 ====================

def add_message(session_id: int, role: str, content: str) -> int:
    """存一条消息（role 只能是 user 或 assistant），返回消息 id"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_messages(session_id: int) -> list[dict]:
    """取某个会话的全部消息，按发送顺序排列（多轮对话记忆就用它拼历史）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ==================== 线索卡片（leads）相关操作 ====================

def create_lead(
    session_id: int,
    requirement: str,
    budget: str,
    timeline: str,
    contact: str,
    summary: str,
) -> int:
    """存一张线索卡片，返回卡片 id"""
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO leads (session_id, requirement, budget, timeline, contact, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, requirement, budget, timeline, contact, summary, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_lead_by_session(session_id: int) -> dict | None:
    """查某个会话的线索卡片（一个会话只有一张），没有返回 None"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM leads WHERE session_id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_leads() -> list[dict]:
    """列出所有线索卡片，最新的在最前面"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_lead(lead_id: int) -> bool:
    """删除一张线索卡片，返回是否真的删掉了（id 不存在时返回 False）"""
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        return cur.rowcount > 0  # rowcount = 实际删掉的行数
    finally:
        conn.close()
