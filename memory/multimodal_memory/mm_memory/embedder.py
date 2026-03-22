"""多模态记忆系统 — Embedding 计算"""
from __future__ import annotations
import json, math, os, sys
from typing import List, Optional

import requests

# ── API 配置 ─────────────────────────────────────────────

_DEFAULT_API_BASE = "https://api.bianxie.ai/v1"
_DEFAULT_EMBED_MODEL = "gemini-embedding-2-preview"
_EMBED_DIMENSIONS: Optional[int] = None  # None = 使用模型默认维度


def _get_config() -> dict:
    """获取 oai_config2 配置（embedding 用）"""
    try:
        proj_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        if proj_root not in sys.path:
            sys.path.insert(0, proj_root)
        from mykey import oai_config2  # type: ignore
        return oai_config2
    except Exception:
        return {}


def _get_api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if key:
        return key
    return _get_config().get("apikey", "")


def _get_api_base() -> str:
    base = _get_config().get("apibase", "")
    if base:
        return base.rstrip("/")
    return _DEFAULT_API_BASE


def _get_embed_model() -> str:
    return _get_config().get("model", _DEFAULT_EMBED_MODEL)


def _post_json(url: str, payload: dict, api_key: str, timeout: int = 30) -> dict:
    """统一 POST JSON 请求"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── Embedding API 调用 ───────────────────────────────────

def _call_embedding_api(input_data, model: str = "",
                        dimensions: Optional[int] = _EMBED_DIMENSIONS,
                        timeout: int = 30) -> dict:
    """统一 embedding API 调用（支持文本和 data URI）"""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("未找到 API Key，请设置环境变量或配置 mykey.py")

    if not model:
        model = _get_embed_model()

    url = f"{_get_api_base()}/embeddings"
    payload: dict = {
        "model": model,
        "input": input_data,
        "encoding_format": "float",
    }
    if dimensions is not None:
        payload["dimensions"] = dimensions

    try:
        return _post_json(url, payload, api_key, timeout=timeout)
    except Exception as e:
        raise RuntimeError(f"Embedding API 调用失败: {e}") from e


def embed_text(text: str, model: str = "",
               dimensions: Optional[int] = _EMBED_DIMENSIONS) -> List[float]:
    """计算单段文本的 embedding 向量"""
    result = _call_embedding_api(text, model, dimensions)
    return result["data"][0]["embedding"]


def embed_image(image_path: str, model: str = "",
                dimensions: Optional[int] = _EMBED_DIMENSIONS) -> List[float]:
    """计算图片的 embedding 向量（利用多模态 embedding 模型）

    将图片转为 data URI 格式传入 embedding API。
    要求模型支持多模态 embedding（如 gemini-embedding-2-preview）。
    """
    import base64, mimetypes
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        mime = "image/png"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_uri = f"data:{mime};base64,{b64}"

    result = _call_embedding_api(data_uri, model, dimensions, timeout=60)
    return result["data"][0]["embedding"]


def embed_image_from_bytes(raw_bytes: bytes, mime_type: str = "image/png",
                           model: str = "",
                           dimensions: Optional[int] = _EMBED_DIMENSIONS) -> List[float]:
    """计算图片字节数据的 embedding 向量（从内存字节数据计算）"""
    import base64
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    data_uri = f"data:{mime_type};base64,{b64}"

    result = _call_embedding_api(data_uri, model, dimensions, timeout=60)
    return result["data"][0]["embedding"]


def embed_texts(texts: List[str], model: str = "",
                dimensions: Optional[int] = _EMBED_DIMENSIONS) -> List[List[float]]:
    """批量计算 embedding（仅支持文本）"""
    if not texts:
        return []

    all_embeddings: List[List[float]] = []
    batch_size = 25

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        result = _call_embedding_api(batch, "", dimensions, timeout=60)
        sorted_data = sorted(result["data"], key=lambda x: x["index"])
        all_embeddings.extend([d["embedding"] for d in sorted_data])

    return all_embeddings


# ── 向量工具函数 ──────────────────────────────────────────

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(vec_a) != len(vec_b):
        raise ValueError(f"向量维度不匹配: {len(vec_a)} vs {len(vec_b)}")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def serialize_vector(vec: List[float]) -> str:
    """将向量序列化为紧凑字符串（用于 SQLite 存储）"""
    return json.dumps(vec)


def deserialize_vector(s: str) -> List[float]:
    """从字符串反序列化向量"""
    return json.loads(s)