"""
FastAPI 主入口：定义全部 API 路由，把前端页面和数据库、AI 串起来。

分层关系（各层各管一件事）：
前端(static/) → 调接口 → main.py（本文件，路由层） → database.py（数据库） + ai.py（AI）
main.py 自己不写 SQL，也不直接调 DeepSeek，只负责"接请求、调函数、返回结果"。
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ai
import auth
import database as db
from config import AUTH_SIGNUP_CODE


# ===== 启动钩子：服务一启动就建表（表不存在才建，已存在不动）=====
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AI 销售助手", lifespan=lifespan)

# 挂载静态文件目录：浏览器访问 /static/style.css 就能拿到文件
app.mount("/static", StaticFiles(directory="static"), name="static")


# ===== 前端页面 =====
@app.get("/")
def home():
    """聊天页"""
    return FileResponse("static/index.html")


@app.get("/leads")
def leads_page():
    """线索管理页（页面本身不拦截，前端加载时会检查登录状态，未登录跳转 /login）"""
    return FileResponse("static/leads.html")


@app.get("/login")
def login_page():
    """登录/注册页"""
    return FileResponse("static/login.html")


# ===== 请求体定义 =====
# Pydantic 模型：FastAPI 会自动把前端传来的 JSON 校验成这个结构
class ChatRequest(BaseModel):
    content: str  # 访客发的消息内容


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    signup_code: str  # 注册邀请码（防止陌生人随便注册账号看线索）


# ==================== 登录认证相关 ====================

# 存放登录令牌的 cookie 名字（登录成功后设置，浏览器之后每次请求自动带上）
AUTH_COOKIE = "auth_token"


def current_user(request: Request) -> dict:
    """
    身份检查（FastAPI 的"依赖"机制）：
    所有需要登录的接口在参数里写 user: dict = Depends(current_user)，
    FastAPI 就会先执行这个函数——从 cookie 里取出令牌查用户，
    查不到就抛 401（未登录），查到了才继续执行接口逻辑。
    """
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    user = db.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def _set_auth_cookie(response: Response, token: str) -> None:
    """把登录令牌写进浏览器 cookie（30 天有效，httponly 防止脚本偷令牌）"""
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=30 * 24 * 3600,  # 30 天
        httponly=True,           # 只有浏览器能携带，页面 JS 读不到（防 XSS 偷令牌）
        samesite="lax",          # 防止跨站请求伪造（CSRF）
    )


@app.post("/api/auth/register")
def register(req: RegisterRequest, response: Response):
    """
    注册新账号：
    1. 校验用户名/密码长度、邀请码是否正确、用户名是否被占用
    2. 密码加盐哈希后存库（数据库里只有哈希，没有明文）
    3. 注册成功直接视为已登录（发令牌、写 cookie）
    """
    username = req.username.strip()
    password = req.password

    if not (2 <= len(username) <= 20):
        raise HTTPException(status_code=400, detail="用户名长度需在 2~20 个字符之间")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if not AUTH_SIGNUP_CODE:
        raise HTTPException(status_code=400, detail="管理员未开放注册")
    if req.signup_code.strip() != AUTH_SIGNUP_CODE:
        raise HTTPException(status_code=400, detail="邀请码错误")
    if db.get_user_by_username(username) is not None:
        raise HTTPException(status_code=400, detail="用户名已被注册")

    salt = auth.new_salt()
    password_hash = auth.hash_password(password, salt)
    user_id = db.create_user(username, password_hash, salt)

    token = auth.generate_token()
    db.create_token(token, user_id)
    _set_auth_cookie(response, token)
    return {"ok": True, "username": username}


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    """登录：校验用户名密码，成功则发令牌写 cookie"""
    user = db.get_user_by_username(req.username.strip())
    # 用户名不存在时也走同样的校验流程，不让攻击者通过报错差异猜出哪个用户名存在
    if user is None or not auth.verify_password(req.password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = auth.generate_token()
    db.create_token(token, user["id"])
    _set_auth_cookie(response, token)
    return {"ok": True, "username": user["username"]}


@app.post("/api/auth/logout")
def logout(request: Request):
    """登出：删除令牌（立刻失效）并清除浏览器 cookie"""
    token = request.cookies.get(AUTH_COOKIE)
    if token:
        db.delete_token(token)
    response = Response()
    response.delete_cookie(AUTH_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    """查询当前登录用户（前端用它判断"我登录了没"）"""
    return {"username": user["username"]}


# ==================== 会话相关接口 ====================

@app.post("/api/sessions")
def create_session():
    """新建一个会话，返回会话 id（前端拿到 id 后用它发消息）"""
    session_id = db.create_session()
    return {"id": session_id, "title": "新对话"}


@app.get("/api/sessions")
def list_sessions(user: dict = Depends(current_user)):
    """
    列出所有会话（最新的在前）——⚠️ 需要登录（老板视角）。
    顺带给每个会话标注 has_lead：这个会话是否已经生成了线索卡片。
    访客自己的历史会话由前端存在浏览器里（localStorage），不经过这个接口。
    """
    sessions = db.list_sessions()
    for s in sessions:
        s["has_lead"] = db.get_lead_by_session(s["id"]) is not None
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: int):
    """取某个会话的全部消息（按发送顺序），前端打开旧会话时用它恢复聊天记录"""
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"messages": db.get_messages(session_id)}


# ==================== 聊天核心接口 ====================

@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: int, req: ChatRequest):
    """
    访客发一条消息，返回 AI 的回复。这是整个应用的核心接口，流程：

    1. 把访客的消息存进数据库
    2. 取出这个会话的全部历史（多轮对话记忆的关键）
    3. 带上历史调 DeepSeek，生成 AI 回复并入库
    4. 如果这个会话还没有线索卡片，让 AI 判断 4 项信息是否集齐：
       集齐 → 生成线索卡片入库，一起返回给前端
    """
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 第 1 步：存访客消息；如果是第一句话，顺手把会话标题设成它的前 20 个字
    db.add_message(session_id, "user", content)
    if len(db.get_messages(session_id)) == 1:
        db.update_session_title(session_id, content[:20])

    # 第 2 步：取出全部历史，格式转成 ai.chat() 需要的 [{"role":..., "content":...}]
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in db.get_messages(session_id)
    ]

    # 第 3 步：调 AI 生成回复并入库
    # 注意：AI 失败时访客消息已经存了（记录真实发生过的对话），但要把错误明确告诉前端，
    # 不能装作成功——错误处理不静默失败。
    try:
        reply = ai.chat(history)
    except Exception as e:
        print(f"[错误] AI 生成回复失败（会话 {session_id}）: {e}")
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用：{e}") from e

    db.add_message(session_id, "assistant", reply)

    # 第 4 步：如果还没有线索卡片，让 AI 判断 4 项信息是否集齐
    lead = db.get_lead_by_session(session_id)
    if lead is None:
        try:
            extracted = ai.extract_lead(history, strict=True)
        except Exception as e:
            # 提取失败不影响聊天（回复已经生成了），但必须打日志，方便排查
            print(f"[错误] 线索提取失败（会话 {session_id}）: {e}")
            extracted = None

        if extracted:
            db.create_lead(
                session_id,
                extracted["requirement"],
                extracted["budget"],
                extracted["timeline"],
                extracted["contact"],
                extracted["summary"],
            )
            lead = db.get_lead_by_session(session_id)

    return {"reply": reply, "lead": lead}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int):
    """
    手动结束对话（兜底）：访客点「结束对话」按钮时调用。
    不管 4 项信息齐不齐都生成线索卡片，缺的字段填"未提供"。
    如果这个会话已经有卡片了，直接返回现有卡片（不会重复生成）。
    """
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    existing = db.get_lead_by_session(session_id)
    if existing:
        return {"lead": existing}

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in db.get_messages(session_id)
    ]

    try:
        extracted = ai.extract_lead(history, strict=False)
    except Exception as e:
        print(f"[错误] 手动提取线索失败（会话 {session_id}）: {e}")
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用：{e}") from e

    db.create_lead(
        session_id,
        extracted["requirement"],
        extracted["budget"],
        extracted["timeline"],
        extracted["contact"],
        extracted["summary"],
    )
    return {"lead": db.get_lead_by_session(session_id)}


# ==================== 线索卡片接口 ====================

@app.get("/api/leads")
def list_leads(user: dict = Depends(current_user)):
    """列出所有线索卡片（最新的在前）——⚠️ 需要登录（线索是客户隐私，只给老板看）"""
    return {"leads": db.list_leads()}


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, user: dict = Depends(current_user)):
    """删除一张线索卡片——⚠️ 需要登录"""
    ok = db.delete_lead(lead_id)
    if not ok:
        raise HTTPException(status_code=404, detail="线索不存在")
    return {"ok": True}


# ===== 本地运行入口：python main.py 直接启动 =====
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
