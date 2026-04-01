"""
embedder.py – 基于 dashscope HTTP API 的多模态 embedding 模块
使用 qwen3-vl-embedding 模型，支持文本和图片的独立/融合向量化

API 接口保持不变：
  embed_text(text)             → List[float]
  embed_image(image_path)      → List[float]
  embed_image_from_bytes(data) → List[float]
  embed_texts(texts)           → List[List[float]]
  cosine_similarity(a, b)      → float
"""

import base64
import math
import mimetypes
import os
from typing import List, Optional

import requests

from mykey import oai_config2 as _cfg

# ── 配置 ──────────────────────────────────────────────
_API_KEY: str = _cfg.get("apikey", "") or _cfg.get("api_key", "")
_MODEL: str = _cfg.get("model", "qwen3-vl-embedding")
_API_URL: str = (
    "https://dashscope.aliyuncs.com"
    "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
)
# 向量维度：支持 2560(默认), 2048, 1536, 1024, 768, 512, 256
_DIMENSION: Optional[int] = _cfg.get("dimension", None)
_TIMEOUT: int = 60  # 请求超时秒数

# ── 全局 Session（绕过系统代理）──────────────────────
_session = requests.Session()
_session.trust_env = False  # 关键：不读取系统代理，避免 SSL 错误


# ── 核心调用 ──────────────────────────────────────────

def _call_embedding(contents: list) -> List[float]:
    """调用 dashscope 多模态 embedding HTTP API，返回单条向量。

    Args:
        contents: 输入列表，如 [{"text": "..."}] 或 [{"image": "data:..."}]
                  多元素时自动启用融合模式

    Returns:
        embedding 向量 (List[float])
    """
    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": _MODEL,
        "input": {"contents": contents},
        "parameters": {},
    }
    if _DIMENSION is not None:
        payload["parameters"]["dimension"] = _DIMENSION

    resp = _session.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Dashscope embedding API 错误 (HTTP {resp.status_code}): "
            f"{resp.text[:500]}"
        )

    data = resp.json()
    embeddings = data.get("output", {}).get("embeddings", [])
    if not embeddings:
        raise RuntimeError(
            f"Dashscope embedding API 返回空结果: {resp.text[:500]}"
        )

    return embeddings[0]["embedding"]


# ── 图片辅助 ──────────────────────────────────────────

def _image_path_to_data_uri(image_path: str) -> str:
    """将本地图片路径转为 base64 data URI"""
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"图片文件不存在: {abs_path}")

    mime, _ = mimetypes.guess_type(abs_path)
    if not mime:
        mime = "image/png"

    with open(abs_path, "rb") as f:
        raw = f.read()

    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_bytes_to_data_uri(data: bytes, mime_type: str = "image/png") -> str:
    """将图片字节数据转为 base64 data URI"""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


# ── 公开接口 ──────────────────────────────────────────

def embed_text(text: str) -> List[float]:
    """将文本转换为向量"""
    if not text or not text.strip():
        raise ValueError("embed_text: 文本不能为空")
    return _call_embedding([{"text": text}])


def embed_image(image_path: str) -> List[float]:
    """将图片文件转换为向量（传入本地路径或 URL）"""
    if not image_path:
        raise ValueError("embed_image: 路径不能为空")

    if image_path.startswith(("http://", "https://")):
        # 远程 URL 直接传
        return _call_embedding([{"image": image_path}])
    else:
        # 本地文件 → base64 data URI
        data_uri = _image_path_to_data_uri(image_path)
        return _call_embedding([{"image": data_uri}])


def embed_image_from_bytes(data: bytes, mime_type: str = "image/png") -> List[float]:
    """将图片字节数据转换为向量"""
    if not data:
        raise ValueError("embed_image_from_bytes: 数据不能为空")
    data_uri = _image_bytes_to_data_uri(data, mime_type)
    return _call_embedding([{"image": data_uri}])


def embed_text_and_image(
    text: str = "",
    image_path: str = "",
    image_data: Optional[bytes] = None,
    mime_type: str = "image/png",
) -> List[float]:
    """将文本和图片融合为一个向量（多模态融合 embedding）

    至少提供 text 或 image_path/image_data 之一。
    当同时提供文本和图片时，API 会生成融合向量。
    """
    contents: list = []

    if text and text.strip():
        contents.append({"text": text})

    if image_data:
        data_uri = _image_bytes_to_data_uri(image_data, mime_type)
        contents.append({"image": data_uri})
    elif image_path:
        if image_path.startswith(("http://", "https://")):
            contents.append({"image": image_path})
        else:
            data_uri = _image_path_to_data_uri(image_path)
            contents.append({"image": data_uri})

    if not contents:
        raise ValueError("embed_text_and_image: 至少提供文本或图片")

    return _call_embedding(contents)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量将文本转换为向量（逐条调用）"""
    return [embed_text(t) for t in texts]


# ── 工具函数 ──────────────────────────────────────────

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)