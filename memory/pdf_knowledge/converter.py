"""
converter.py – PDF 转图片模块
使用 pdf2image (poppler) 将 PDF 每页渲染为 PNG 图片
"""

import os
import uuid
from typing import List, Tuple

from pdf2image import convert_from_path

# 默认页面图片存储根目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PAGES_DIR = os.path.join(_BASE_DIR, "pages")


def pdf_to_images(
    pdf_path: str,
    pdf_id: str = "",
    dpi: int = 200,
    fmt: str = "png",
    progress_callback=None,
) -> Tuple[str, List[str]]:
    """将 PDF 文件的每一页转换为图片并保存。

    Args:
        pdf_path: PDF 文件路径
        pdf_id: 文档唯一 ID（为空则自动生成）
        dpi: 渲染分辨率，默认 200（清晰且文件不会太大）
        fmt: 输出图片格式，默认 png
        progress_callback: 可选进度回调 callback(current, total)

    Returns:
        (pdf_id, image_paths): 文档 ID 和每页图片路径列表
    """
    from pdf2image import pdfinfo_from_path

    abs_path = os.path.abspath(pdf_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"PDF 文件不存在: {abs_path}")

    if not pdf_id:
        pdf_id = uuid.uuid4().hex[:12]

    # 创建该文档的页面目录
    doc_dir = os.path.join(_PAGES_DIR, pdf_id)
    os.makedirs(doc_dir, exist_ok=True)

    # 先获取总页数
    info = pdfinfo_from_path(abs_path)
    total_pages = info.get("Pages", 0)

    # 逐页转换，每页都回调进度
    image_paths: List[str] = []
    for i in range(1, total_pages + 1):
        images = convert_from_path(
            abs_path, dpi=dpi, fmt=fmt,
            first_page=i, last_page=i,
        )
        if images:
            page_path = os.path.join(doc_dir, f"page_{i:03d}.{fmt}")
            images[0].save(page_path, fmt.upper())
            image_paths.append(page_path)
        if progress_callback:
            try:
                progress_callback(i, total_pages)
            except Exception:
                pass

    return pdf_id, image_paths


def get_page_count(pdf_path: str) -> int:
    """快速获取 PDF 页数（不渲染图片）"""
    from pdf2image import pdfinfo_from_path
    info = pdfinfo_from_path(pdf_path)
    return info.get("Pages", 0)


def get_thumbnail(pdf_path: str, pdf_id: str = "", size: int = 300,
                  first_page_image: str = "") -> str:
    """生成 PDF 第一页的缩略图，用于前端预览。

    Args:
        pdf_path: PDF 文件路径
        pdf_id: 文档 ID
        size: 缩略图最大边长（像素）
        first_page_image: 可选，已有的第一页图片路径（避免重复渲染）

    Returns:
        缩略图文件路径
    """
    from PIL import Image

    if not pdf_id:
        pdf_id = uuid.uuid4().hex[:12]

    thumb_dir = os.path.join(_PAGES_DIR, pdf_id)
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_path = os.path.join(thumb_dir, "thumbnail.png")

    if first_page_image and os.path.exists(first_page_image):
        # 直接从已有的第一页图片缩放，无需重新渲染 PDF
        img = Image.open(first_page_image)
    else:
        # 回退：渲染第一页
        abs_path = os.path.abspath(pdf_path)
        images = convert_from_path(abs_path, dpi=72, first_page=1, last_page=1)
        if not images:
            return thumb_path
        img = images[0]

    img.thumbnail((size, size))
    img.save(thumb_path, "PNG")
    return thumb_path