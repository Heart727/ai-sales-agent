"""
FastAPI 主入口：定义全部 API 路由，把前端页面和数据库、AI 串起来。

分层关系（各层各管一件事）：
前端(static/) → 调接口 → main.py（本文件，路由层） → database.py（数据库） + ai.py（AI）
main.py 自己不写 SQL，也不直接调 DeepSeek，只负责"接请求、调函数、返回结果"。
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import secrets
import hmac
import config
import security

import ai
import auth
import database as db
import rate_limit
from config import AUTH_SIGNUP_CODE


# ===== 启动钩子：服务一启动就建表（表不存在才建，已存在不动）=====
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AI 销售助手", lifespan=lifespan)
app.add_middleware(security.RequestGuard)

# 挂载静态文件目录：浏览器访问 /static/style.css 就能拿到文件
app.mount("/static", StaticFiles(directory="static"), name="static")


# ===== 限流统一响应：任何接口抛 RateLimited 异常，统一转成 429 =====
# Retry-After 是 HTTP 标准响应头：告诉客户端"建议多久后再试"，
# 浏览器、爬虫、脚本都认识这个头，比只回一句中文更规范。
@app.exception_handler(rate_limit.RateLimited)
async def rate_limited_handler(request: Request, exc: rate_limit.RateLimited):
    return JSONResponse(
        status_code=429,
        content={"detail": exc.detail},
        headers={"Retry-After": str(exc.retry_after)},
    )


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
    content: str = Field(min_length=1, max_length=config.MAX_MESSAGE_CHARS)  # 访客发的消息内容


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    signup_code: str = Field(max_length=256)  # 注册邀请码（防止陌生人随便注册账号看线索）


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
        secure=config.COOKIE_SECURE,
        httponly=True,           # 只有浏览器能携带，页面 JS 读不到（防 XSS 偷令牌）
        samesite="lax",          # 配合 RequestGuard 的来源校验
    )


@app.post("/api/auth/register")
def register(req: RegisterRequest, response: Response, request: Request):
    rate_limit.check_auth_rate(rate_limit.get_client_ip(request), req.username)
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
    if not hmac.compare_digest(req.signup_code.strip().encode(), AUTH_SIGNUP_CODE.encode()):
        raise HTTPException(status_code=400, detail="邀请码错误")
    if db.get_user_by_username(username) is not None:
        raise HTTPException(status_code=400, detail="用户名已被注册")

    salt = auth.new_salt()
    password_hash = auth.hash_password(password, salt)
    try:
        user_id = db.create_user(username, password_hash, salt)
    except db.INTEGRITY_ERRORS:
        raise HTTPException(status_code=400, detail="用户名已被注册")

    token = auth.generate_token()
    db.create_token(token, user_id)
    _set_auth_cookie(response, token)
    return {"ok": True, "username": username}


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response, request: Request):
    rate_limit.check_auth_rate(rate_limit.get_client_ip(request), req.username)
    """登录：校验用户名密码，成功则发令牌写 cookie"""
    user = db.get_user_by_username(req.username.strip())
    # 用户名不存在时也走同样的校验流程，不让攻击者通过报错差异猜出哪个用户名存在
    valid = auth.verify_password(req.password, user["salt"] if user else "0"*32, user["password_hash"] if user else "0"*64)
    if user is None or not valid:
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
    response = JSONResponse({"ok": True})
    response.delete_cookie(AUTH_COOKIE, secure=config.COOKIE_SECURE, httponly=True, samesite="lax")
    return response


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    """查询当前登录用户（前端用它判断"我登录了没"）"""
    return {"username": user["username"]}


# ==================== 会话相关接口 ====================

@app.post("/api/sessions")
def create_session(request: Request, response: Response):
    """
    新建一个会话，返回会话 id（前端拿到 id 后用它发消息）。
    ⚠️ 防刷：每个 IP 每天建的会话数有限，超限返回 429。
    """
    ip = rate_limit.get_client_ip(request)
    rate_limit.check_ban(ip)
    rate_limit.check_session_creation(ip)

    token = request.cookies.get("visitor_token")
    if security.owner_hash(token) is None:
        token = secrets.token_hex(32)
    session_id = db.create_session(owner_hash=security.owner_hash(token))
    response.set_cookie("visitor_token", token, max_age=30*86400, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="lax")
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
def get_messages(session_id: int, request: Request):
    require_session(session_id, request, allow_admin=True)
    """取某个会话的全部消息（按发送顺序），前端打开旧会话时用它恢复聊天记录"""
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"messages": db.get_messages(session_id)}


# ==================== 聊天核心接口 ====================

def require_session(session_id: int, request: Request, allow_admin=False):
    session = db.get_session(session_id)
    owner = security.owner_hash(request.cookies.get("visitor_token"))
    if session and owner and session.get("owner_hash") and hmac.compare_digest(owner, session["owner_hash"]):
        return session
    if session and allow_admin and db.get_user_by_token(request.cookies.get(AUTH_COOKIE, "")):
        return session
    # Same status for missing and inaccessible IDs; old sessions remain admin-only.
    raise HTTPException(status_code=404, detail="会话不存在或无权访问")


def admit(request):
    ip = rate_limit.get_client_ip(request)
    rate_limit.check_ban(ip)
    rate_limit.check_message_rate(ip)
    rate_limit.check_global_quota(ip)
    rate_limit.check_daily_message_quota(ip)


def save_lead(session_id, extracted):
    if not isinstance(extracted, dict):
        raise HTTPException(status_code=502, detail="线索提取暂时失败，请稍后重试")
    fields = ("requirement", "budget", "timeline", "contact", "summary")
    if any(not isinstance(extracted.get(k), str) or len(extracted[k]) > 4000 for k in fields):
        raise HTTPException(status_code=502, detail="线索格式无效，请稍后重试")
    db.create_lead(session_id, *(extracted[k] for k in fields))
    return db.get_lead_by_session(session_id)


def history_for(session_id, finalizing=False):
    history = [{"role":m["role"],"content":m["content"]} for m in db.get_messages(session_id)]
    if sum(len(m["content"]) for m in history) > config.MAX_HISTORY_CHARS + (8000 if finalizing else 0):
        raise HTTPException(status_code=400, detail="对话内容已达上限，请新建对话")
    return history


@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: int, req: ChatRequest, request: Request):
    require_session(session_id, request)
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")
    with security.lease(f"session:{session_id}"):
        rate_limit.check_session_message_cap(session_id)
        history = history_for(session_id)
        if sum(len(m["content"]) for m in history) + len(content) > config.MAX_HISTORY_CHARS:
            raise HTTPException(status_code=400, detail="对话内容已达上限，请新建对话")
        admit(request)
        db.add_message(session_id, "user", content)
        if not history:
            db.update_session_title(session_id, content[:20])
        history.append({"role":"user", "content":content})
        try:
            reply = ai.chat(history)
            if not reply or len(reply)>8000:
                raise ValueError("Invalid AI reply")
        except rate_limit.RateLimited:
            raise
        except Exception:
            raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后重试")
        db.add_message(session_id, "assistant", reply)
        # 线索只在访客点击“结束对话”时整理，避免一次请求连续调用两次模型。
        # 这样公开演示的 Vercel Hobby Function 不会因第二次 AI 调用超时。
        lead = db.get_lead_by_session(session_id)
        warning = None
        return {"reply":reply, "lead":lead, "warning":warning}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int, request: Request):
    require_session(session_id, request)
    with security.lease(f"session:{session_id}"):
        existing = db.get_lead_by_session(session_id)
        if existing:
            return {"lead":existing}
        history = history_for(session_id, finalizing=True)
        if not history:
            raise HTTPException(status_code=400, detail="请先描述您的需求，再结束对话")
        admit(request)
        try:
            extracted = ai.extract_lead(history, strict=False)
        except rate_limit.RateLimited:
            raise
        except Exception:
            raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后重试")
        return {"lead":save_lead(session_id, extracted)}


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

    uvicorn.run(app, host="127.0.0.1", port=8000, proxy_headers=False)
