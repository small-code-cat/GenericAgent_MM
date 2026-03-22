"""多模态记忆系统 — 知识提取器（MLLM 调用）"""
from __future__ import annotations
import base64, json, mimetypes, os, re, sys
from typing import Optional

import requests as _requests

# ── 配置 ──────────────────────────────────────────────────

_DEFAULT_API_BASE = "https://api.bianxie.ai/v1"
_DEFAULT_CHAT_MODEL = "claude-opus-4-6"  # 支持多模态，文本+图片统一用同一模型

_EXTRACT_PROMPT = """你是一个知识提取助手。请从以下内容中提取关键知识，输出 JSON 格式：
{
  "image_description": "简洁的图片内容描述（仅含图片时填写，纯文本输入留空字符串）",
  "knowledge": "对内容的精简综合理解（提炼核心要点，不超过200字）"
}

要求：
1. image_description 只描述图片视觉内容，精简扼要
2. knowledge 是对图文内容的综合理解和提炼，精简但保留核心信息
3. 只输出 JSON，不要其他内容"""


def _get_config() -> dict:
    """获取 claude_config 配置（多模态对话用）"""
    try:
        proj_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        if proj_root not in sys.path:
            sys.path.insert(0, proj_root)
        from mykey import claude_config  # type: ignore
        return claude_config
    except Exception:
        return {}


def _get_api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if key:
        return key
    return _get_config().get("apikey", "")


def _get_chat_model() -> str:
    """从 claude_config 获取 chat 模型名"""
    return _get_config().get("model", _DEFAULT_CHAT_MODEL)


def _get_api_base() -> str:
    base = _get_config().get("apibase", "")
    if base:
        return base.rstrip("/")
    return _DEFAULT_API_BASE


def _image_to_base64_parts(image_path: str):
    """将本地图片转为 Claude API 格式的 base64 部分"""
    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        mime = "image/png"
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}


def _post_json(url: str, payload: dict, api_key: str, timeout: int = 120) -> dict:
    """统一 POST JSON 请求"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = _requests.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        # Proxy may return 400 for multimodal requests but body contains valid response
        try:
            data = resp.json()
            if "choices" in data:
                return data
        except Exception:
            pass
        resp.raise_for_status()
    return resp.json()


def _convert_anthropic_content_to_openai(content):
    """将 Anthropic 格式的 content 块转换为 OpenAI 兼容格式"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    # content 是 list of blocks
    parts = []
    for block in content:
        btype = block.get("type", "")
        if btype == "text":
            parts.append({"type": "text", "text": block.get("text", "")})
        elif btype == "image":
            # Anthropic: {"type":"image","source":{"type":"base64","media_type":...,"data":...}}
            # OpenAI:    {"type":"image_url","image_url":{"url":"data:mime;base64,..."}}
            src = block.get("source", {})
            mime = src.get("media_type", "image/png")
            data = src.get("data", "")
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data}"}
            })
        else:
            parts.append(block)
    return parts


def _call_chat(messages: list, model: str = "",
               temperature: float = 0.3, timeout: int = 120) -> str:
    """调用 OpenAI 兼容 API（支持多模态图片）"""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("未找到 API Key")

    if not model:
        model = _get_chat_model()

    # 转换消息格式为 OpenAI 兼容格式
    openai_messages = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        openai_messages.append({
            "role": role,
            "content": _convert_anthropic_content_to_openai(content),
        })

    # OpenAI 兼容 API（兼容 base 末尾有无 /v1 的情况）
    base = _get_api_base()
    if base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": openai_messages,
        "temperature": temperature,
        "max_tokens": 4096,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = _requests.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        err_text = resp.text[:500]
        raise RuntimeError(f"Chat API HTTP {resp.status_code}: {err_text}")
    result = resp.json()
    # 解析 OpenAI 兼容响应: {"choices": [{"message": {"content": "..."}}]}
    choices = result.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    # fallback: 尝试 Anthropic 格式
    content = result.get("content", [])
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if b.get("type") == "text"
        )
    return str(result)


# ── 知识提取 ─────────────────────────────────────────────

def extract_from_text(text: str, context: str = "") -> dict:
    """从纯文本提取结构化知识

    Returns: {"image_description": str, "knowledge": str}
    """
    user_text = text
    if context:
        user_text = f"[上下文] {context}\n\n{text}"

    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": user_text},
    ]

    raw = _call_chat(messages)
    return _parse_json_response(raw, text)


def extract_from_image(image_path: str, context: str = "") -> dict:
    """从图片提取结构化知识（调用 Claude 多模态 API）

    Returns: {"image_description": str, "knowledge": str}
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        mime = "image/png"
    with open(image_path, "rb") as f:
        raw_bytes = f.read()

    return extract_from_image_bytes(raw_bytes, mime, context)


def extract_from_image_bytes(raw_bytes: bytes, mime_type: str = "image/png",
                               context: str = "") -> dict:
    """从图片字节数据提取结构化知识（从内存字节数据提取）"""
    img_part = {
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type, "data": base64.b64encode(raw_bytes).decode("utf-8")}
    }
    user_content = [img_part]
    if context:
        user_content.append({"type": "text", "text": f"[上下文] {context}"})
    user_content.append({"type": "text", "text": "请提取这张图片中的关键知识。"})

    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw = _call_chat(messages)
    return _parse_json_response(raw, "[图片字节数据]")


def extract_from_image_and_text_bytes(raw_bytes: bytes, mime_type: str,
                                       text: str, context: str = "") -> dict:
    """从图片字节+文本混合提取知识"""
    img_part = {
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type,
                   "data": base64.b64encode(raw_bytes).decode("utf-8")}
    }
    user_content = [img_part, {"type": "text", "text": text}]
    if context:
        user_content.insert(0, {"type": "text", "text": f"[上下文] {context}"})

    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw = _call_chat(messages)
    return _parse_json_response(raw, text)


def _parse_json_response(raw: str, fallback_content: str) -> dict:
    """解析 LLM 返回的 JSON，容错处理
    
    Returns: {
        "image_description": str, "knowledge": str
    }
    """
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        data = json.loads(text)
        return {
            "image_description": data.get("image_description", ""),
            "knowledge": data.get("knowledge", "") or data.get("content", fallback_content),
        }
    except json.JSONDecodeError:
        pass

    # ── regex fallback: 处理 LLM 返回含未转义引号等格式问题的 JSON ──
    img_desc = ""
    knowledge = ""
    # 贪婪匹配每个字段：从 "field": " 开始，到下一个 "field" 或 } 结束前的内容
    m = re.search(
        r'"image_description"\s*:\s*"(.*?)"\s*(?:,\s*"|\'\s*})',
        text, re.DOTALL,
    )
    if not m:
        # 更宽松：匹配到行尾逗号或 } 之前
        m = re.search(
            r'"image_description"\s*:\s*"(.+?)"\s*[,}]',
            text, re.DOTALL,
        )
    if m:
        img_desc = m.group(1).replace('\\n', '\n').strip()

    m2 = re.search(
        r'"knowledge"\s*:\s*"(.*?)"\s*[,}]',
        text, re.DOTALL,
    )
    if not m2:
        # 最宽松：匹配到字符串末尾
        m2 = re.search(
            r'"knowledge"\s*:\s*"(.+)',
            text, re.DOTALL,
        )
        if m2:
            val = m2.group(1).rstrip().rstrip('}').rstrip().rstrip('"').strip()
            knowledge = val.replace('\\n', '\n')
    else:
        knowledge = m2.group(1).replace('\\n', '\n').strip()

    if img_desc or knowledge:
        return {
            "image_description": img_desc,
            "knowledge": knowledge or fallback_content,
        }

    return {
        "image_description": "",
        "knowledge": raw or fallback_content,
    }