"""
全局配置模块：从 .env 文件读取配置，导出给其他模块使用。

为什么要有这个文件？
1. API Key 属于敏感信息，不能直接写死在代码里（写死了传到 GitHub 上就会被盗用）。
   正确做法：放在 .env 文件里（.env 在 .gitignore 里，不会上传），代码从这里读取。
2. 所有配置集中在一个文件，改配置不用满项目找代码。
"""
import os

from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件，把它里面的内容变成"环境变量"
# 这样下面的 os.getenv() 才能读到
load_dotenv()

# ===== DeepSeek API 配置 =====
# os.getenv("名字", "默认值")：从环境变量里取"名字"的值，取不到就用默认值
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

# 兼容旧配置：deepseek-chat 是已过时的别名，DeepSeek 不会报错，
# 而是静默映射到弱模型 deepseek-v4-flash，导致悄悄降级。
# 这里主动纠正，无论 .env 里写的是哪个旧值，最终都用 v4-pro。
if DEEPSEEK_MODEL == "deepseek-chat":
    DEEPSEEK_MODEL = "deepseek-v4-pro"

# ===== 登录注册配置 =====
# 注册邀请码：注册新账号时必须填这个码。
# 如果没有邀请码限制，任何人都能注册账号看线索，等于没锁门。
AUTH_SIGNUP_CODE = os.getenv("AUTH_SIGNUP_CODE", "")

# ===== 防刷限流配置（商用标准：全部可用环境变量覆盖，方便部署时调参）=====
# 每个 IP 每分钟最多发几条消息（正常人类聊天远达不到）
RATE_MSG_PER_MINUTE = int(os.getenv("RATE_MSG_PER_MINUTE", "8"))
# 每个 IP 每天最多发几条消息（防慢速刷：一分钟一条刷一天也会封）
RATE_MSG_PER_DAY = int(os.getenv("RATE_MSG_PER_DAY", "100"))
# 每个 IP 每天最多新建几个会话
RATE_SESSIONS_PER_DAY = int(os.getenv("RATE_SESSIONS_PER_DAY", "20"))
# 每个会话最多几条消息（一次真实销售对话 10~20 条就结束了）
RATE_MSG_PER_SESSION = int(os.getenv("RATE_MSG_PER_SESSION", "60"))
# 全局兜底：整个服务每天最多处理多少条消息（防多 IP 分布式攻击打穿 AI 额度）
RATE_GLOBAL_MSG_PER_DAY = int(os.getenv("RATE_GLOBAL_MSG_PER_DAY", "5000"))
# 触发日配额封禁的时长（小时）
BAN_HOURS = int(os.getenv("BAN_HOURS", "24"))
# 是否信任反向代理传来的 X-Forwarded-For 头。
# 直连部署（默认）：False——攻击者伪造 XFF 无效，用真实连接 IP 计数；
# 部署在 Nginx/云网关后面：必须设 True，否则所有请求都显示网关 IP。
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes")

# ===== 数据库配置 =====
# SQLite 数据库就是一个文件，放在项目根目录下，叫 sales_agent.db
# __file__ 是当前文件（config.py）的完整路径，dirname 取它所在的目录 = 项目根目录
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "sales_agent.db"))

# Production security controls; explicit proxy allowlist, never trust arbitrary XFF.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "").rstrip("/")
TRUSTED_PROXY_IPS = os.getenv("TRUSTED_PROXY_IPS", "").split(",")
MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_CHARS = 16000
MAX_BODY_BYTES = 32768
AI_MAX_CONCURRENT = int(os.getenv("AI_MAX_CONCURRENT", "4"))
AI_DAILY_UNITS = int(os.getenv("AI_DAILY_UNITS", "200000"))
AI_DAILY_CALLS = int(os.getenv("AI_DAILY_CALLS", "500"))
