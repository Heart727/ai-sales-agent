import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import turso_serverless
import database as db
import main
import rate_limit

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = str(Path(self.tmp.name) / 'test.db')
        db.init_db()
        self.a = TestClient(main.app)
        self.b = TestClient(main.app)
        self.chat = patch('ai.chat', return_value='hello').start()
        self.extract = patch('ai.extract_lead', return_value={'requirement':'site','budget':'1','timeline':'soon','contact':'test','summary':'test'}).start()
    def tearDown(self):
        patch.stopall()
        self.a.close(); self.b.close()
        db.DB_PATH = self.old
        self.tmp.cleanup()
    def session(self):
        return self.a.post('/api/sessions').json()['id']
    def test_other_visitor_cannot_read_or_write(self):
        sid = self.session()
        self.assertEqual(self.a.get(f'/api/sessions/{sid}/messages').status_code, 200)
        for method, suffix, kwargs in [('get','messages',{}), ('post','messages',{'json':{'content':'hi'}}), ('post','end',{})]:
            self.assertEqual(getattr(self.b,method)(f'/api/sessions/{sid}/{suffix}', **kwargs).status_code,404)
        self.chat.assert_not_called(); self.extract.assert_not_called()
    def test_login_throttled(self):
        codes = [self.a.post('/api/auth/login',json={'username':'missing','password':'wrong-password'}).status_code for _ in range(12)]
        self.assertIn(429,codes)
    def test_oversized_message_rejected(self):
        sid = self.session()
        self.assertEqual(self.a.post(f'/api/sessions/{sid}/messages',json={'content':'x'*5000}).status_code,422)
        self.chat.assert_not_called()
    def test_global_exhaustion_does_not_ban_visitor(self):
        with patch.object(rate_limit,'RATE_GLOBAL_MSG_PER_DAY',0):
            with self.assertRaises(rate_limit.RateLimited): rate_limit.check_global_quota('192.0.2.1')
        self.assertIsNone(db.get_ban('192.0.2.1'))
    def test_end_obeys_global_quota(self):
        sid = self.session()
        db.add_message(sid,'user','hello')
        with patch.object(rate_limit,'RATE_GLOBAL_MSG_PER_DAY',0):
            self.assertEqual(self.a.post(f'/api/sessions/{sid}/end').status_code,429)
        self.extract.assert_not_called()

    def test_registration_throttled(self):
        codes=[self.a.post('/api/auth/register',json={'username':'someone','password':'long-password','signup_code':'wrong'}).status_code for _ in range(12)]
        self.assertIn(429,codes)
    def test_logout_clears_cookie(self):
        self.a.cookies.set('auth_token','invalid')
        response=self.a.post('/api/auth/logout')
        self.assertIn('Max-Age=0',response.headers.get('set-cookie',''))
    def test_cross_origin_write_rejected(self):
        self.assertEqual(self.a.post('/api/sessions',headers={'Origin':'https://evil.example'}).status_code,403)
    def test_large_body_rejected(self):
        self.assertEqual(self.a.post('/api/sessions',content=b'x'*40000).status_code,413)
    def test_session_busy_rejected_before_ai(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        sid=self.session()
        entered=threading.Event(); release=threading.Event()
        def slow(history):
            entered.set(); release.wait(5); return 'hello'
        self.chat.side_effect=slow
        with ThreadPoolExecutor() as pool:
            first=pool.submit(self.a.post,f'/api/sessions/{sid}/messages',json={'content':'hello'})
            try:
                self.assertTrue(entered.wait(3))
                second=self.a.post(f'/api/sessions/{sid}/messages',json={'content':'again'})
                self.assertEqual(second.status_code,429)
            finally: release.set()
            self.assertEqual(first.result().status_code,200)
    def test_untrusted_proxy_ignored(self):
        from starlette.requests import Request
        req=Request({'type':'http','client':('192.0.2.9',123),'headers':[(b'x-forwarded-for',b'1.2.3.4')]})
        with patch.object(rate_limit,'TRUST_PROXY',True):
            self.assertEqual(rate_limit.get_client_ip(req),'192.0.2.9')

    def test_empty_end_does_not_create_lead(self):
        sid=self.session()
        self.assertEqual(self.a.post(f'/api/sessions/{sid}/end').status_code,400)
        self.assertIsNone(db.get_lead_by_session(sid))
    def test_login_logout_and_expiry(self):
        with patch.object(main,'AUTH_SIGNUP_CODE','test-invite'):
            response=self.a.post('/api/auth/register',json={'username':'owner','password':'long-password','signup_code':'test-invite'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.a.get('/api/leads').status_code,200)
        token=self.a.cookies.get('auth_token')
        conn=db.get_conn()
        conn.execute("UPDATE tokens SET created_at='2000-01-01 00:00:00'"); conn.commit(); conn.close()
        self.assertEqual(self.a.get('/api/leads').status_code,401)
        self.assertEqual(self.a.post('/api/auth/login',json={'username':'owner','password':'long-password'}).status_code,200)
        token=self.a.cookies.get('auth_token')
        self.assertEqual(self.a.post('/api/auth/logout').status_code,200)
        self.a.cookies.set('auth_token',token)
        self.assertEqual(self.a.get('/api/leads').status_code,401)

    def test_remote_unique_conflict_returns_bad_request(self):
        with patch.object(main, 'AUTH_SIGNUP_CODE', 'test-invite'), \
             patch.object(db, 'get_user_by_username', return_value=None), \
             patch.object(db, 'create_user', side_effect=turso_serverless.IntegrityError('duplicate')):
            response = self.a.post('/api/auth/register', json={
                'username': 'owner',
                'password': 'long-password',
                'signup_code': 'test-invite',
            })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], '用户名已被注册')
    def test_normal_conversation_and_card_idempotency(self):
        sid=self.session()
        r=self.a.post(f'/api/sessions/{sid}/messages',json={'content':'hello'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(self.a.get(f'/api/sessions/{sid}/messages').json()['messages']),2)
        self.assertIsNone(r.json()['lead'])
        self.extract.assert_not_called()
        card = self.a.post(f'/api/sessions/{sid}/end').json()['lead']
        self.assertIsNotNone(card['id'])
        self.assertEqual(len(db.list_leads()),1)
    def test_old_sessions_not_claimed(self):
        sid=db.create_session()
        self.session()
        self.assertEqual(self.a.get(f'/api/sessions/{sid}/messages').status_code,404)
    def test_proxy_chain_uses_last_untrusted_hop(self):
        import config
        from starlette.requests import Request
        req=Request({'type':'http','client':('127.0.0.1',1),'headers':[(b'x-forwarded-for',b'6.6.6.6, 192.0.2.20')]})
        with patch.object(rate_limit,'TRUST_PROXY',True), patch.object(config,'TRUSTED_PROXY_IPS',['127.0.0.1/32']):
            self.assertEqual(rate_limit.get_client_ip(req),'192.0.2.20')
    def test_budget_persists_across_initialization(self):
        self.assertTrue(db.reserve_ai_budget(50,2,100))
        db.init_db()
        self.assertTrue(db.reserve_ai_budget(50,2,100))
        self.assertFalse(db.reserve_ai_budget(1,2,100))
    def test_concurrent_budget_reservations(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted=list(pool.map(lambda _:db.reserve_ai_budget(10,3,30),range(12)))
        self.assertEqual(sum(accepted),3)
    def test_ai_budget_rejection_never_reaches_provider(self):
        import config, security
        from unittest.mock import Mock
        client=Mock()
        with patch.object(config,'AI_DAILY_UNITS',1):
            with self.assertRaises(rate_limit.RateLimited):
                security.completion(client,messages=[{'content':'hello'}],max_tokens=10)
        client.chat.completions.create.assert_not_called()
    def test_ai_failure_releases_slot_but_keeps_charge(self):
        import security
        from unittest.mock import Mock
        client=Mock()
        client.chat.completions.create.side_effect=RuntimeError('upstream')
        with self.assertRaises(RuntimeError):
            security.completion(client,messages=[{'content':'hello'}],max_tokens=10)
        conn=db.get_conn()
        self.assertEqual(conn.execute('SELECT count(*) FROM security_leases').fetchone()[0],0)
        self.assertEqual(conn.execute('SELECT calls FROM ai_budgets').fetchone()[0],1)
        conn.close()
    def test_ai_concurrency_limit_rejects_before_provider(self):
        import config, security
        from unittest.mock import Mock
        client=Mock()
        with patch.object(config,'AI_MAX_CONCURRENT',1), security.lease('ai'):
            with self.assertRaises(rate_limit.RateLimited):
                security.completion(client,messages=[{'content':'hello'}],max_tokens=10)
        client.chat.completions.create.assert_not_called()
    def test_migration_preserves_old_messages(self):
        conn=db.get_conn()
        conn.executescript("DROP TABLE sessions; CREATE TABLE sessions(id INTEGER PRIMARY KEY, title TEXT, created_at TEXT); INSERT INTO sessions VALUES(123,'old','2020-01-01');")
        conn.close()
        db.add_message(123,'user','keep me')
        db.init_db(); db.init_db()
        self.assertEqual(db.get_messages(123)[0]['content'],'keep me')
        self.assertIsNone(db.get_session(123)['owner_hash'])

    def test_rejected_creation_does_not_charge_global(self):
        for _ in range(12): self.a.post('/api/sessions')
        conn=db.get_conn()
        count=conn.execute("SELECT count FROM rate_limits WHERE key='global:session:day'").fetchone()[0]
        conn.close()
        self.assertEqual(count,5)
    def test_exhausted_service_retries_do_not_ban(self):
        sid=self.session()
        with patch.object(rate_limit,'RATE_GLOBAL_MSG_PER_DAY',0), patch.object(rate_limit,'RATE_MSG_PER_DAY',1):
            for _ in range(3):
                self.assertEqual(self.a.post(f'/api/sessions/{sid}/messages',json={'content':'hi'}).status_code,429)
        self.assertIsNone(db.get_ban('testclient'))
    def test_long_reply_still_allows_finalization(self):
        sid=self.session()
        db.add_message(sid,'user','x'*15000)
        self.chat.return_value='y'*2000
        self.extract.return_value=None
        self.assertEqual(self.a.post(f'/api/sessions/{sid}/messages',json={'content':'hi'}).status_code,200)
        self.extract.return_value={'requirement':'site','budget':'1','timeline':'soon','contact':'test','summary':'test'}
        self.assertEqual(self.a.post(f'/api/sessions/{sid}/end').status_code,200)

if __name__ == '__main__': unittest.main()
