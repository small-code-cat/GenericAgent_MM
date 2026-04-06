"""
searcher.py – PDF 知识库向量检索模块
基于 embedder.py 的 cosine_similarity 对 PDF 页面进行语义搜索
"""

import os
import sys
from typing import List

# ── 导入 embedder（需要调整路径）──────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, "..", ".."))
_MM_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "memory", "multimodal_memory", "mm_memory")

# 确保能 import embedder 和 mykey
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _MM_MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MM_MEMORY_DIR)

from embedder import embed_text, embed_image, cosine_similarity
from memory.pdf_knowledge.store import (
    SearchResult,
    get_all_pages_with_embeddings,
    get_pages,
    get_document,
    list_documents,
)


def search_by_text(
    query: str,
    top_k: int = 3,
    threshold: float = 0.0,
    pdf_id: str = "",
) -> List[SearchResult]:
    """用文本查询检索最相关的 PDF 页面

    Args:
        query: 用户查询文本
        top_k: 返回最相关的前 K 个结果
        threshold: 最低相似度阈值（低于此值不返回）
        pdf_id: 可选，限定在某个文档内搜索

    Returns:
        按相似度降序排列的 SearchResult 列表
    """
    # 1. 计算查询文本的 embedding
    query_emb = embed_text(query)

    # 2. 获取候选页面
    if pdf_id:
        pages = get_pages(pdf_id)
        pages = [p for p in pages if p.embedding]
    else:
        pages = get_all_pages_with_embeddings()

    if not pages:
        return []

    # 3. 计算相似度并排序
    scored: List[SearchResult] = []
    for page in pages:
        score = cosine_similarity(query_emb, page.embedding)
        if score >= threshold:
            doc = get_document(page.pdf_id)
            fname = doc.filename if doc else ""
            scored.append(SearchResult(
                pdf_id=page.pdf_id,
                page_num=page.page_num,
                image_path=page.image_path,
                score=score,
                filename=fname,
            ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def search_by_image(
    image_path: str,
    top_k: int = 3,
    threshold: float = 0.0,
    pdf_id: str = "",
) -> List[SearchResult]:
    """用图片检索最相关的 PDF 页面

    Args:
        image_path: 查询图片路径
        top_k: 返回最相关的前 K 个结果
        threshold: 最低相似度阈值
        pdf_id: 可选，限定在某个文档内搜索

    Returns:
        按相似度降序排列的 SearchResult 列表
    """
    query_emb = embed_image(image_path)

    if pdf_id:
        pages = get_pages(pdf_id)
        pages = [p for p in pages if p.embedding]
    else:
        pages = get_all_pages_with_embeddings()

    if not pages:
        return []

    scored: List[SearchResult] = []
    for page in pages:
        score = cosine_similarity(query_emb, page.embedding)
        if score >= threshold:
            doc = get_document(page.pdf_id)
            fname = doc.filename if doc else ""
            scored.append(SearchResult(
                pdf_id=page.pdf_id,
                page_num=page.page_num,
                image_path=page.image_path,
                score=score,
                filename=fname,
            ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]