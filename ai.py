"""
AI 对话逻辑：负责调用 DeepSeek API 做两件事。

1. chat()：生成销售助手的回复
   把"系统提示词 + 会话全部历史"发给 DeepSeek，拿到 AI 回复。
   历史必须带上，否则 AI 不知道访客之前说过什么（多轮对话记忆）。

2. extract_lead()：从对话里提取线索卡片
   再调一次 DeepSeek，让它把 需求/预算/时间/联系方式 整理成 JSON。
   两种模式：
   - strict=True  （自动判断）：四项信息集齐才输出 JSON，没集齐输出 NOT_READY
   - strict=False （手动结束兜底）：不管集没集齐都输出 JSON，缺的字段填"未提供"

为什么用 openai 官方 SDK 而不是自己发 HTTP 请求？
DeepSeek 的接口是"OpenAI 兼容"的，openai SDK 只要把 base_url 指过去就能用，
比自己拼 HTTP 请求省事、少出错。
"""
import json
from security import completion

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

# 创建 DeepSeek 客户端（openai SDK 指向 DeepSeek 的地址）
# 这里只创建一次，后面反复复用，不用每次都新建
client = OpenAI(api_key=DEEPSEEK_API_KEY or "not-configured", base_url=DEEPSEEK_BASE_URL, timeout=45, max_retries=0)

# ===== 销售助手的系统提示词 =====
# 系统提示词的作用：告诉 AI "你是谁、你的任务是什么、什么话术"。
# 访客看不到这段话，但 AI 每一轮都会"记住"它。
SYSTEM_PROMPT = """你是一位热情、专业的销售助理，负责在网站上接待访客（第一轮接待）。
你的任务是通过自然友好的对话，逐步了解客户的以下 4 项信息：
1. 需求：客户想买什么/解决什么问题
2. 预算：客户愿意花多少钱
3. 时间：客户希望什么时候开始/完成
4. 联系方式：电话、微信或邮箱（方便后续跟进）

对话规则：
- 用简洁的中文，像真人客服一样自然交流，不要列问题清单逼问
- 一次最多问 1-2 个问题，先聊需求和预算，时间和联系方式放在后面问
- 客户还没说清楚的，就顺着他的话追问；聊偏了就把话题温柔地带回来
- 4 项信息都收集到之后，感谢客户，告诉他会尽快安排专人联系
- 不要编造公司信息、价格或承诺，不知道就说不确定"""

# 提取线索时用的提示词（让 AI 输出 JSON）
EXTRACT_PROMPT_STRICT = """下面是销售助理和客户的对话记录。请判断是否已经收集齐以下 4 项信息：
需求、预算、时间、联系方式。
- 如果 4 项都收集到了，输出一个 JSON（不要输出任何其他文字）：
{"requirement": "客户需求", "budget": "预算", "timeline": "时间要求", "contact": "联系方式", "summary": "一句话总结整个需求"}
- 如果没有收集齐，只输出一个单词：NOT_READY"""

EXTRACT_PROMPT_FORCE = """下面是销售助理和客户的对话记录。请从中提取以下 4 项信息：
需求、预算、时间、联系方式。
输出一个 JSON（不要输出任何其他文字）：
{"requirement": "...", "budget": "...", "timeline": "...", "contact": "...", "summary": "一句话总结"}
对话里没提到的字段，值填"未提供"；summary 用一句话概括客户的需求和情况。"""


def _check_api_key():
    """API Key 没配置时直接抛错（不静默失败，让接口层把错误提示给前端）"""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，请检查 .env 文件")


def chat(history: list[dict]) -> str:
    """
    生成销售助手回复。

    参数 history：这个会话到目前为止的全部消息（不含系统提示词），
    格式：[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

    返回：AI 回复的文字
    """
    _check_api_key()
    # 把系统提示词放在最前面，后面接全部历史
    # AI 每一轮都能看到之前所有对话，这就是"多轮对话记忆"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    resp = completion(client,
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=0.7,    # 0.7：回复自然一些，不要死板（0 是最死板，1 是最放飞）
        max_tokens=1500,    # 回复最长 1500 token（deepseek-v4-pro 是推理模型，推理也占额度，要留够）
    )
    return resp.choices[0].message.content or ""


def extract_lead(messages: list[dict], strict: bool = True) -> dict | None:
    """
    从对话里提取线索卡片。

    参数 messages：对话历史（不含系统提示词）
    参数 strict：
      True  = 自动判断模式：4 项信息没集齐返回 None（继续聊，不生成卡片）
      False = 手动结束模式：信息不齐也生成，缺的字段填"未提供"

    返回：{"requirement":..., "budget":..., "timeline":..., "contact":..., "summary":...}
          或 None（仅 strict=True 且信息未集齐时）
    """
    _check_api_key()
    prompt = EXTRACT_PROMPT_STRICT if strict else EXTRACT_PROMPT_FORCE

    # 把对话记录拼成文字发给 AI
    transcript = "\n".join(
        f"{'客户' if m['role'] == 'user' else '销售'}：{m['content']}" for m in messages
    )

    resp = completion(client,
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你负责从对话中提取客户信息，输出 JSON。"},
            {"role": "user", "content": prompt + "\n\n对话记录：\n" + transcript},
        ],
        temperature=0,      # 提取信息要稳定，用 0（每次输出尽量一致）
        max_tokens=800,
    )
    text = (resp.choices[0].message.content or "").strip()

    # 自动判断模式下，AI 明确说没集齐 → 返回 None，不生成卡片
    if strict and text.upper().startswith("NOT_READY"):
        return None

    return _parse_json_card(text)


def _parse_json_card(text: str) -> dict:
    """
    把 AI 输出的文字解析成 JSON 字典。

    AI 有时会在 JSON 外面包一层 ```json ... ``` 代码块标记，或者前后加多余的话，
    所以解析策略是：找到第一个 { 和最后一个 }，只解析中间那段。
    解析失败就抛错——宁可报错让开发者知道，也不静默吞掉（那样线索会悄悄丢）。
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"AI 输出的内容里没有合法的 JSON：{text[:200]}")

    raw = text[start : end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI 输出的 JSON 解析失败：{e}，原文：{raw[:200]}") from e

    # 把缺失的字段补成"未提供"，避免后面存库时报错
    for field in ("requirement", "budget", "timeline", "contact", "summary"):
        data.setdefault(field, "未提供")
    return data
