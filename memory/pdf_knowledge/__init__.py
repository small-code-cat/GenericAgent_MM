"""
pdf_knowledge – PDF 知识库模块
提供 PDF 上传→转图片→embedding→存储→检索 的完整流程

公开接口:
  ingest_pdf(pdf_path, filename) → dict   上传并处理 PDF
  search_knowledge(query, ...) → list      文本检索 PDF 页面
  list_pdfs() → list                       列出所有已入库文档
  delete_pdf(pdf_id) → None                删除文档
"""

import os
import sys

# 确保项目根目录在 sys.path 中（embedder 和 mykey 需要）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, "..", ".."))
_MM_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "memory", "multimodal_memory", "mm_memory")

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _MM_MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MM_MEMORY_DIR)

from typing import List, Optional

from memory.pdf_knowledge.converter import pdf_to_images, get_thumbnail
from memory.pdf_knowledge.store import (
    PDFDocument,
    PDFPage,
    SearchResult,
    save_document,
    save_page,
    get_document,
    list_documents,
    delete_document,
    get_pages,
)
from memory.pdf_knowledge.searcher import search_by_text, search_by_image


def ingest_pdf(pdf_path: str, filename: str = "", pdf_id: str = "",
               progress_callback=None) -> dict:
    """处理 PDF 文件：转图片 → 计算 embedding → 存储

    Args:
        pdf_path: PDF 文件路径
        filename: 原始文件名（为空则从路径提取）
        pdf_id: 可选文档 ID
        progress_callback: 可选进度回调 callback(stage, current, total, message)
            stage: 'convert' | 'embed' | 'done' | 'error'

    Returns:
        {
            "pdf_id": str,
            "filename": str,
            "page_count": int,
            "thumbnail": str,  # 缩略图路径
            "status": "success" | "error",
            "message": str,
        }
    """
    from embedder import embed_image  # 延迟导入，避免循环

    def _progress(stage, current=0, total=0, message=""):
        if progress_callback:
            try:
                progress_callback(stage, current, total, message)
            except Exception:
                pass

    if not filename:
        filename = os.path.basename(pdf_path)

    try:
        # 1. PDF → 图片（逐页转换，带进度回调）
        _progress('convert', 0, 0, '正在获取 PDF 信息...')

        def _convert_progress(current, total):
            _progress('convert', current, total,
                      f'转换图片中 {current}/{total} 页...')

        pdf_id, image_paths = pdf_to_images(
            pdf_path, pdf_id=pdf_id,
            progress_callback=_convert_progress,
        )
        page_count = len(image_paths)

        # 2. 生成缩略图（复用已有的第一页图片，无需重新渲染）
        first_img = image_paths[0] if image_paths else ""
        thumb_path = get_thumbnail(pdf_path, pdf_id=pdf_id,
                                   first_page_image=first_img)

        # 3. 保存文档元数据
        save_document(pdf_id, filename, page_count, thumbnail_path=thumb_path)
        _progress('embed', 0, page_count, f'开始处理 {page_count} 页 embedding...')

        # 4. 逐页计算 embedding 并保存
        for i, img_path in enumerate(image_paths, start=1):
            _progress('embed', i, page_count,
                      f'向量化 {i}/{page_count} 页...')
            try:
                emb = embed_image(img_path)
            except Exception as e:
                print(f"[pdf_knowledge] 第 {i} 页 embedding 失败: {e}")
                emb = []
            save_page(pdf_id, i, img_path, emb)

        _progress('done', page_count, page_count, f'成功处理 {page_count} 页')
        return {
            "pdf_id": pdf_id,
            "filename": filename,
            "page_count": page_count,
            "thumbnail": thumb_path,
            "status": "success",
            "message": f"成功处理 {page_count} 页",
        }

    except Exception as e:
        _progress('error', 0, 0, str(e))
        return {
            "pdf_id": pdf_id or "",
            "filename": filename,
            "page_count": 0,
            "thumbnail": "",
            "status": "error",
            "message": str(e),
        }


def search_knowledge(
    query: str,
    top_k: int = 3,
    threshold: float = 0.0,
    pdf_id: str = "",
) -> List[dict]:
    """文本检索 PDF 知识库

    Args:
        query: 查询文本
        top_k: 返回前 K 个结果
        threshold: 最低相似度阈值
        pdf_id: 可选，限定在某个文档内搜索

    Returns:
        [{"pdf_id", "page_num", "image_path", "score", "filename"}, ...]
    """
    results = search_by_text(query, top_k=top_k, threshold=threshold, pdf_id=pdf_id)
    return [
        {
            "pdf_id": r.pdf_id,
            "page_num": r.page_num,
            "image_path": r.image_path,
            "score": round(r.score, 4),
            "filename": r.filename,
        }
        for r in results
    ]


def list_pdfs() -> List[dict]:
    """列出所有已入库的 PDF 文档"""
    docs = list_documents()
    return [
        {
            "pdf_id": d.pdf_id,
            "filename": d.filename,
            "page_count": d.page_count,
            "created_at": d.created_at,
            "thumbnail": d.thumbnail_path,
        }
        for d in docs
    ]


def delete_pdf(pdf_id: str):
    """删除指定文档及其所有数据"""
    # 删除页面图片文件
    pages = get_pages(pdf_id)
    for p in pages:
        if os.path.exists(p.image_path):
            os.remove(p.image_path)

    # 删除缩略图
    doc = get_document(pdf_id)
    if doc and doc.thumbnail_path and os.path.exists(doc.thumbnail_path):
        os.remove(doc.thumbnail_path)

    # 删除文档目录
    pages_dir = os.path.join(_BASE_DIR, "pages", pdf_id)
    if os.path.isdir(pages_dir):
        import shutil
        shutil.rmtree(pages_dir, ignore_errors=True)

    # 删除数据库记录
    delete_document(pdf_id)


def get_pdf_info(pdf_id: str) -> Optional[dict]:
    """获取单个文档信息"""
    doc = get_document(pdf_id)
    if not doc:
        return None
    return {
        "pdf_id": doc.pdf_id,
        "filename": doc.filename,
        "page_count": doc.page_count,
        "created_at": doc.created_at,
        "thumbnail": doc.thumbnail_path,
    }