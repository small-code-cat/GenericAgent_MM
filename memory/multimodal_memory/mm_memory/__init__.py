"""多模态记忆系统 (Multimodal Memory)

用法:
    import sys; sys.path.append("/path/to/memory/multimodal_memory")
    from mm_memory import MemoryEngine, memorize, recall

    # 存入文本记忆
    items = memorize("Python的GIL是全局解释器锁，限制多线程并行")

    # 存入图片记忆（传文件路径，自动复制到 images/ 目录 + 保存绝对路径）
    items = memorize(image_path="/path/to/screenshot.png")

    # 存入文本+图片记忆
    items = memorize("这是架构图说明", image_path="/path/to/photo.jpg")

    # 语义检索（文本）
    results = recall("Python多线程为什么慢")

    # 语义检索（图片路径）
    results = recall(image_path="/path/to/ui.png")
"""
from typing import List, Optional, Dict, Any
from .models import KnowledgeItem, SearchResult
from .engine import MemoryEngine, get_engine

__all__ = [
    "KnowledgeItem", "SearchResult",
    "MemoryEngine", "get_engine",
    "memorize", "memorize_raw", "recall", "forget", "forget_group",
    "get_group", "list_memories",
    "get_image_path_by_group", "image_count",
    "show_image",
    "unique_images",
    # 底层工具
    "embed_text", "embed_image", "embed_image_from_bytes", "embed_texts",
    "cosine_similarity",
    "extract_from_text", "extract_from_image", "extract_from_image_bytes",
    "extract_from_image_and_text",
]


# ── 自动探测用户上传图片 ──────────────────────────────────

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

def _auto_detect_latest_upload() -> Optional[str]:
    """扫描 temp/uploads/ 目录，返回最新上传的图片文件路径（60秒内），否则返回 None"""
    import os, time
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.abspath(os.path.join(_pkg_dir, "..", "..", ".."))
    uploads_dir = os.path.join(_project_root, "temp", "uploads")
    if not os.path.isdir(uploads_dir):
        return None
    candidates = []
    now = time.time()
    for fname in os.listdir(uploads_dir):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in _IMAGE_EXTS:
            continue
        fpath = os.path.join(uploads_dir, fname)
        mtime = os.path.getmtime(fpath)
        if now - mtime <= 60:
            candidates.append((mtime, fpath))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ── 便捷函数（使用全局引擎） ─────────────────────────────

def memorize(content: str = "",
            image_path: Optional[str] = None,
            context: str = "",
            auto_extract: bool = True,
            **kwargs) -> str:
    """存入记忆（自动提取知识 + 多模态 embedding）

    一次调用最多生成3条记录（source_text / source_image / knowledge），
    共享同一个 group_id 进行关联。

    图片通过 image_path（文件路径）传入，复制到 images/ 目录并保存绝对路径。

    Args:
        content: 文本内容（别名: text / desc / description）
        image_path: 图片文件路径（别名: image_file / img_path），复制到 images/ 目录
        context: 额外上下文
        auto_extract: 是否用 LLM 自动提取知识

    Returns:
        str: 对 agent 友好的结果摘要字符串
    """
    # 兼容常见别名：text / desc / description → content
    if not content:
        content = kwargs.get("text") or kwargs.get("desc") or kwargs.get("description") or ""
    # 兼容 image_file / img_path → image_path
    if image_path is None:
        image_path = kwargs.get("image_file") or kwargs.get("img_path") or None
    # 自动探测 temp/uploads/ 中最新上传的图片
    if image_path is None:
        image_path = _auto_detect_latest_upload()
    if image_path:
        image_path = str(image_path)

    # ── 查重：recall检索，按group计算平均分，≥0.8则跳过存储 ──
    _dedup_query = content or ""
    _dedup_results = []
    if _dedup_query:
        try:
            _dedup_results = get_engine().recall(_dedup_query, top_k=10, threshold=0.35, expand_groups=True)
        except Exception:
            pass
    elif image_path:
        try:
            import os as _os
            if _os.path.isfile(image_path):
                with open(image_path, "rb") as _f:
                    _img_bytes = _f.read()
                _ext = _os.path.splitext(image_path)[1].lower()
                _mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
                _dedup_results = get_engine().recall("", image_data=_img_bytes, mime_type=_mime_map.get(_ext, "image/png"),
                                                     top_k=10, threshold=0.35, expand_groups=True)
        except Exception:
            pass
    if _dedup_results:
        from collections import defaultdict
        _group_scores = defaultdict(list)
        for _r in _dedup_results:
            if _r.group_id:
                _group_scores[_r.group_id].append(_r.score)
        for _gid, _scores in _group_scores.items():
            _avg = sum(_scores) / len(_scores)
            if _avg >= 0.8:
                print(f"[mm_memory] 查重跳过：group {_gid} 平均分 {_avg:.3f} >= 0.8，已有相似记忆")
                return f"[记忆跳过] 已存在相似记忆(group={_gid}, 相似度={_avg:.2f})，无需重复存储。"

    items = get_engine().memorize(content, image_path=image_path, context=context, auto_extract=auto_extract)
    # 构建 agent 友好的结果摘要
    parts = []
    for it in items:
        label = {"source_text": "原文", "source_image": "图片", "knowledge": "知识"}.get(it.embed_type, it.embed_type)
        preview = it.content[:80] + ("..." if len(it.content) > 80 else "")
        parts.append(f"  - [{label}] {preview}")
    summary = f"[记忆已存储] group={items[0].group_id if items else '?'}, 共{len(items)}条记录:\n" + "\n".join(parts)
    return summary


def memorize_raw(content: str,
                source_type: str = "text",
                embed_type: str = "knowledge",
                group_id: str = "") -> KnowledgeItem:
    """直接存入记忆(跳过 LLM, 仅 embedding)"""
    return get_engine().memorize_raw(content, source_type=source_type,
                                     embed_type=embed_type, group_id=group_id)


def recall(query: str = "",
           image_data: Optional[bytes] = None,
           mime_type: str = "image/png",
           top_k: int = 5, threshold: float = 0.35,
           source_type=None,
           expand_groups: bool = True,
           **kwargs) -> List[SearchResult]:
    """语义检索记忆(支持多模态联合检索)

    Args:
        query: 文本查询（可选）
        image_data: 图片字节数据（可选，也可通过 image_path 传文件路径）
        image_path: 图片文件路径（别名: image_file / img_path），自动读取转 bytes
        mime_type: image_data 的 MIME 类型
        top_k: 每个查询向量返回的最大结果数
        threshold: 相似度阈值
        source_type: 过滤来源类型
        expand_groups: 是否通过 group_id 关联扩展结果

    Returns:
        List[SearchResult]: 检索结果（已通过 group 关联扩展 + 去重）
    """
    # 兼容 image_path / image_file / img_path → 自动读取文件转为 image_data
    if image_data is None:
        image_path = kwargs.get("image_path") or kwargs.get("image_file") or kwargs.get("img_path") or ""
        if image_path:
            import os
            image_path = str(image_path)
            if os.path.isfile(image_path):
                with open(image_path, "rb") as f:
                    image_data = f.read()
                # 自动推断 mime_type
                ext = os.path.splitext(image_path)[1].lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
                mime_type = mime_map.get(ext, mime_type)
    return get_engine().recall(query, image_data=image_data, mime_type=mime_type,
                              top_k=top_k, threshold=threshold,
                              source_type=source_type,
                              expand_groups=expand_groups)


def forget(memory_id: str) -> bool:
    """删除一条记忆"""
    return get_engine().forget(memory_id)


def forget_group(group_id: str) -> int:
    """删除同一组的所有关联记忆及图片文件

    Returns:
        int: 删除的记录数
    """
    return get_engine().forget_group(group_id)


def get_group(group_id: str) -> List[KnowledgeItem]:
    """获取同一组的所有关联记忆"""
    return get_engine().get_group(group_id)


def list_memories(limit: int = 50, source_type=None):
    """列出记忆"""
    return get_engine().list_memories(limit, source_type=source_type)


# ── 图片文件读取 ───────────────────────────────────────

def get_image_path_by_group(group_id: str) -> Optional[str]:
    """根据 group_id 获取关联图片的文件路径

    Returns:
        图片文件绝对路径，或 None
    """
    return get_engine().get_image_path(group_id)


def image_count() -> int:
    """返回已存储的图片文件数量"""
    return get_engine().image_count()


def show_image(group_id: str = "", image_path: str = "") -> bool:
    """显示记忆关联的图片

    Args:
        group_id: 记忆组 ID（通过组查找关联图片文件）
        image_path: 直接指定图片文件路径

    Returns:
        bool: 是否成功显示
    """
    import os
    # 智能纠正：如果 group_id 看起来像文件路径（含 / 或 \），自动当作 image_path
    if group_id and not image_path:
        if '/' in group_id or '\\' in group_id or '.' in group_id:
            image_path = group_id
            group_id = ""
    path = image_path
    if not path and group_id:
        path = get_image_path_by_group(group_id) or ""
    if not path:
        raise ValueError("必须提供 group_id 或 image_path")

    if not os.path.isfile(path):
        print(f"图片文件不存在: {path}")
        return False

    import subprocess, platform
    if platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    elif platform.system() == "Windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    return True


def unique_images(results: List[SearchResult]) -> List[SearchResult]:
    """按 group_id 去重 recall 结果，每组只保留最高分的记录。

    用于图片展示场景：同一次 memorize 产生的多条记录（text/image/knowledge embedding）
    共享 group_id，展示图片时只需显示一次。

    文本总结场景请直接使用 recall() 的完整结果。

    Args:
        results: recall() 返回的 SearchResult 列表

    Returns:
        List[SearchResult]: 按 group_id 去重后的结果（保留每组最高分项）
    """
    best_per_group: dict[str, SearchResult] = {}
    for r in results:
        gid = r.item.group_id or r.item.id  # 无 group_id 时以自身 id 为组
        if gid not in best_per_group or r.score > best_per_group[gid].score:
            best_per_group[gid] = r
    deduped = list(best_per_group.values())
    deduped.sort(key=lambda r: r.score, reverse=True)
    return deduped


# ── 底层工具便捷访问 ─────────────────────────────────────

def embed_text(text: str, model: str = "", dimensions: int = None) -> List[float]:
    """计算单段文本的 embedding 向量"""
    from .embedder import embed_text as _impl
    return _impl(text, model, dimensions)

def embed_image(image_path: str, model: str = "", dimensions: int = None) -> List[float]:
    """计算图片的 embedding 向量（文件路径方式）"""
    from .embedder import embed_image as _impl
    return _impl(image_path, model, dimensions)

def embed_image_from_bytes(raw_bytes: bytes, mime_type: str = "image/png",
                            model: str = "", dimensions: int = None) -> List[float]:
    """计算图片字节数据的 embedding 向量"""
    from .embedder import embed_image_from_bytes as _impl
    return _impl(raw_bytes, mime_type, model, dimensions)

def embed_texts(texts: List[str], model: str = "", dimensions: int = None) -> List[List[float]]:
    """批量计算文本 embedding"""
    from .embedder import embed_texts as _impl
    return _impl(texts, model, dimensions)

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """计算余弦相似度"""
    from .embedder import cosine_similarity as _impl
    return _impl(vec_a, vec_b)

def extract_from_text(text: str, context: str = "") -> dict:
    """LLM 提取文本知识"""
    from .extractor import extract_from_text as _impl
    return _impl(text, context)

def extract_from_image(image_path: str, context: str = "") -> dict:
    """LLM 提取图片知识（文件路径方式）"""
    from .extractor import extract_from_image as _impl
    return _impl(image_path, context)

def extract_from_image_bytes(raw_bytes: bytes, mime_type: str = "image/png",
                             context: str = "") -> dict:
    """LLM 提取图片知识（字节数据方式）"""
    from .extractor import extract_from_image_bytes as _impl
    return _impl(raw_bytes, mime_type, context)

def extract_from_image_and_text(image_path: str, text: str,
                                 context: str = "") -> dict:
    """LLM 提取图片+文本混合知识（文件路径方式）"""
    import os, mimetypes
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")
    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        mime = "image/png"
    with open(image_path, "rb") as f:
        raw_bytes = f.read()
    from .extractor import extract_from_image_and_text_bytes as _impl
    return _impl(raw_bytes, mime, text, context)
