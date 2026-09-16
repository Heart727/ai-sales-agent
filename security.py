"""Visitor ownership, bounded request bodies, CSRF checks and shared AI admission."""
from contextlib import contextmanager
import hashlib
import re
from urllib.parse import urlsplit
from starlette.responses import JSONResponse
import config
import database as db
from rate_limit import RateLimited


def owner_hash(token):
    if not token or not re.fullmatch(r"[0-9a-f]{64}", token):
        return None
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def lease(resource, capacity=1):
    token = db.acquire_lease(resource, capacity)
    if token is None:
        raise RateLimited("请求正在处理中，请稍后再试", 5)
    try:
        yield
    finally:
        db.release_lease(token)


def completion(client, **kwargs):
    # UTF-8 bytes + framing allowance + output cap: conservative work units,
    # not provider billing tokens or a currency guarantee. No refund on failure.
    units = sum(len(m['content'].encode('utf-8'))+128 for m in kwargs['messages']) + kwargs['max_tokens'] + 512
    with lease('ai', config.AI_MAX_CONCURRENT):
        if not db.reserve_ai_budget(units, config.AI_DAILY_CALLS, config.AI_DAILY_UNITS):
            raise RateLimited("今日 AI 服务额度已用完", 3600)
        return client.chat.completions.create(**kwargs)


class RequestGuard:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        if scope['method'] in ('POST','PUT','PATCH','DELETE'):
            origin = headers.get(b'origin')
            expected = config.PUBLIC_ORIGIN or (scope['scheme']+'://'+headers.get(b'host',b'').decode())
            if origin and origin.decode().rstrip('/') != expected:
                return await JSONResponse({'detail':'不允许跨站提交'},status_code=403)(scope,receive,send)
            if headers.get(b'sec-fetch-site') == b'cross-site':
                return await JSONResponse({'detail':'不允许跨站提交'},status_code=403)(scope,receive,send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body',b''))
            if len(body)>config.MAX_BODY_BYTES:
                return await JSONResponse({'detail':'请求体过大'},status_code=413)(scope,receive,send)
            if not message.get('more_body',False): break
        consumed = False
        async def replay():
            nonlocal consumed
            if consumed: return await receive()
            consumed = True
            return {'type':'http.request','body':bytes(body),'more_body':False}
        await self.app(scope,replay,send)
