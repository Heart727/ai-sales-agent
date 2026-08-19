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

# ===== 数据库配置 =====
# SQLite 数据库就是一个文件，放在项目根目录下，叫 sales_agent.db
# __file__ 是当前文件（config.py）的完整路径，dirname 取它所在的目录 = 项目根目录
DB_PATH = os.path.join(os.path.dirname(__file__), "sales_agent.db")
