"""多模态记忆系统 — 核心引擎（SQLite 存储 + 多模态语义检索）

升级说明:
  - memorize() 现在为每次调用生成最多 3 条记录（source_text / source_image / knowledge），
    共享同一 group_id，用于检索后的关联扩展。
  - recall() 支持文本 + 图片混合查询，多向量联合检索 → group 关联扩展 → 去重。
"""
from __future__ import annotations
import json, os, sqlite3, time, uuid
from typing import List, Optional

from .models import KnowledgeItem, SearchResult
from .embedder import embed_text, embed_image, cosine_similarity
from .extractor import extract_from_text, extract_from_image, extract_from_image_bytes

# ── 默认路径 ─────────────────────────────────────────────

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.dirname(_PKG_DIR)  # multimodal_memory/
_DEFAULT_DB = os.path.join(_DATA_DIR, "mm_data.db")


# ── 数据库初始化 & 迁移 ──────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source_type TEXT DEFAULT 'text',
    source_path TEXT DEFAULT '',
    embedding TEXT DEFAULT '[]',
    created_at REAL DEFAULT 0,
    group_id TEXT DEFAULT '',
    embed_type TEXT DEFAULT 'knowledge'
)
"""

_CREATE_INDEX_SOURCE_TYPE = """
CREATE INDEX IF NOT EXISTS idx_memories_source_type ON memories(source_type)
"""

_CREATE_INDEX_GROUP_ID = """
CREATE INDEX IF NOT EXISTS idx_memories_group_id ON memories(group_id)
"""

_CREATE_INDEX_EMBED_TYPE = """
CREATE INDEX IF NOT EXISTS idx_memories_embed_type ON memories(embed_type)
"""


# (图片改为文件存储到 images/ 目录)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """检查表中是否存在某列"""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _migrate_db(conn: sqlite3.Connection):
    """向旧数据库添加新列（向后兼容）"""
    if not _column_exists(conn, "memories", "group_id"):
        conn.execute("ALTER TABLE memories ADD COLUMN group_id TEXT DEFAULT ''")
        # 旧数据: group_id 设为自身 id
        conn.execute("UPDATE memories SET group_id = id WHERE group_id = '' OR group_id IS NULL")
        conn.commit()

    if not _column_exists(conn, "memories", "embed_type"):
        conn.execute("ALTER TABLE memories ADD COLUMN embed_type TEXT DEFAULT 'knowledge'")
        # 旧数据: 全部视为 knowledge 类型
        conn.execute("UPDATE memories SET embed_type = 'knowledge' WHERE embed_type = '' OR embed_type IS NULL")
        conn.commit()


def _init_db(db_path: str) -> sqlite3.Connection:
    """初始化数据库连接和表"""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_INDEX_SOURCE_TYPE)
    # 先迁移旧表（添加 group_id / embed_type 列），再建索引
    _migrate_db(conn)
    conn.execute(_CREATE_INDEX_GROUP_ID)
    conn.execute(_CREATE_INDEX_EMBED_TYPE)
    # ── 图片文件存储目录 ──
    images_dir = os.path.join(os.path.dirname(db_path) or ".", "images")
    os.makedirs(images_dir, exist_ok=True)
    conn.commit()
    return conn


# ── 全列 SELECT 常量 ─────────────────────────────────────

_SELECT_COLS = ("id, content, source_type, source_path, "
                "embedding, created_at, group_id, embed_type")

_SELECT_COLS_NO_EMBED = ("id, content, source_type, source_path, "
                         "'[]', created_at, group_id, embed_type")


# ── 核心引擎类 ───────────────────────────────────────────

class MemoryEngine:
    """多模态记忆引擎"""

    def __init__(self, db_path: str = _DEFAULT_DB):
        self.db_path = db_path
        self._conn = _init_db(db_path)
        self._images_dir = os.path.join(os.path.dirname(db_path) or ".", "images")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── 内部工具 ─────────────────────────────────────────

    def _insert_item(self, item: KnowledgeItem):
        """将 KnowledgeItem 写入数据库"""
        self._conn.execute(
            "INSERT INTO memories (id, content, source_type, source_path, "
            "embedding, created_at, group_id, embed_type) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (item.id, item.content, item.source_type,
             item.source_path, json.dumps(item.embedding),
             item.created_at, item.group_id, item.embed_type)
        )

    # ── 存入记忆 ─────────────────────────────────────────

    def memorize(self, content: str = "",
                 image_path: Optional[str] = None,
                 context: str = "",
                 auto_extract: bool = True) -> List[KnowledgeItem]:
        """存入一条记忆（多模态版本，图片文件复制到 images/ 目录）

        为一次调用生成最多 3 条记录，共享同一 group_id:
          1. source_text   — 原始文本的 embedding（如有文本输入）
          2. source_image  — 原始图片的 embedding（如有图片输入）
          3. knowledge     — LLM 提取知识的 embedding（始终生成）

        图片以 image_path（文件路径）传入，复制到 images/ 目录并保存绝对路径。

        Args:
            content: 文本内容
            image_path: 图片文件路径，会被复制到 images/ 目录
            context: 额外上下文提示
            auto_extract: 是否用 LLM 自动提取结构化知识

        Returns:
            本次存入的所有 KnowledgeItem 列表
        """
        if not content and not image_path:
            raise ValueError("content 和 image_path 至少提供一个")

        # ── 确定来源类型 ──
        if image_path:
            source_type = "mixed" if content else "image"
        else:
            source_type = "text"

        # ── 图片文件处理：复制到 images/ 目录 ──
        import shutil
        raw_image_bytes: Optional[bytes] = None
        mime_type = "image/png"
        stored_image_path: Optional[str] = None  # 复制后的绝对路径

        # ── 生成 group_id ──
        group_id = uuid.uuid4().hex[:12]
        now = time.time()
        created_items: List[KnowledgeItem] = []

        if image_path:
            image_path = str(image_path)
            if not os.path.isfile(image_path):
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
            try:
                # 保留原始扩展名
                ext = os.path.splitext(image_path)[1].lstrip(".") or "png"
                img_filename = f"{group_id}.{ext}"
                dest_path = os.path.join(self._images_dir, img_filename)
                shutil.copy2(image_path, dest_path)
                stored_image_path = os.path.abspath(dest_path)
                # 推断 mime_type
                mime_map = {
                    "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "gif": "image/gif",
                    "webp": "image/webp", "bmp": "image/bmp",
                }
                mime_type = mime_map.get(ext.lower(), "image/png")
                # 读取 bytes 用于 embedding 计算和 LLM 提取
                with open(dest_path, "rb") as _f:
                    raw_image_bytes = _f.read()
            except FileNotFoundError:
                raise
            except Exception as e:
                print(f"[mm_memory] 复制图片文件失败: {e}")

        # ── 知识提取（传入字节数据，由 embed_image_from_bytes / extract_from_image_bytes 处理）──
        image_description = ""
        knowledge_text = ""
        if auto_extract:
            try:
                if source_type == "mixed":
                    from . import extractor as _ext
                    extracted = _ext.extract_from_image_and_text_bytes(raw_image_bytes or b"", mime_type, content, context)
                elif source_type == "image":
                    from . import extractor as _ext
                    extracted = _ext.extract_from_image_bytes(raw_image_bytes or b"", mime_type, context)
                else:
                    extracted = extract_from_text(content, context)

                image_description = extracted.get("image_description", "")
                knowledge_text = extracted.get("knowledge", "") or content
            except Exception as e:
                knowledge_text = content or "[图片]"

        if not knowledge_text:
            knowledge_text = content or "[图片]"

        # ── 1) source_text embedding ──
        if content:
            try:
                text_embedding = embed_text(content)
                item_src_text = KnowledgeItem(
                    content=content,
                    source_type=source_type,
                    source_path="",
                    embedding=text_embedding,
                    created_at=now,
                    group_id=group_id,
                    embed_type="source_text",
                )
                self._insert_item(item_src_text)
                created_items.append(item_src_text)
            except Exception as e:
                print(f"[mm_memory] source_text embedding 失败: {e}")

        # ── 2) source_image embedding ──
        if raw_image_bytes:
            try:
                from . import embedder as _emb
                img_embedding = _emb.embed_image_from_bytes(raw_image_bytes, mime_type)
                item_src_img = KnowledgeItem(
                    content=image_description or "[图片]",
                    source_type=source_type,
                    source_path=stored_image_path or "",
                    embedding=img_embedding,
                    created_at=now,
                    group_id=group_id,
                    embed_type="source_image",
                )
                self._insert_item(item_src_img)
                created_items.append(item_src_img)
            except Exception as e:
                print(f"[mm_memory] source_image embedding 失败: {e}")

        # ── 3) knowledge embedding（始终生成）──
        try:
            knowledge_embedding = embed_text(knowledge_text)
        except Exception as e:
            raise RuntimeError(f"Knowledge embedding 计算失败: {e}") from e

        item_knowledge = KnowledgeItem(
            content=knowledge_text,
            source_type=source_type,
            source_path="",
            embedding=knowledge_embedding,
            created_at=now,
            group_id=group_id,
            embed_type="knowledge",
        )
        self._insert_item(item_knowledge)
        created_items.append(item_knowledge)

        self._conn.commit()

        return created_items

    def memorize_raw(self, content: str,
                     source_type: str = "text",
                     embed_type: str = "knowledge",
                     group_id: str = "") -> KnowledgeItem:
        """直接存入记忆（跳过 LLM 提取，仅计算 embedding）"""
        embedding = embed_text(content)

        item = KnowledgeItem(
            content=content,
            source_type=source_type,
            embedding=embedding,
            group_id=group_id or "",
            embed_type=embed_type,
        )
        # group_id 未指定时 __post_init__ 会设为 self.id
        self._insert_item(item)
        self._conn.commit()
        return item

    # ── 语义检索（多模态 + 关联扩展 + 去重）────────────────

    def recall(self, query: str = "",
               image_data: Optional[bytes] = None,
               mime_type: str = "image/png",
               top_k: int = 5, threshold: float = 0.5,
               source_type: Optional[str] = None,
               expand_groups: bool = True) -> List[SearchResult]:
        """多模态语义检索记忆

        Args:
            query: 查询文本（可选）
            image_data: 查询图片字节数据（可选）
            mime_type: image_data 的 MIME 类型
            top_k: 初始检索返回最多 k 条结果
            threshold: 最低相似度阈值
            source_type: 过滤来源类型 (text/image/mixed)
            expand_groups: 是否通过 group_id 关联扩展结果

        Returns:
            按相似度降序排列的 SearchResult 列表（已去重）
        """
        if not query and not image_data:
            raise ValueError("query 和 image_data 至少提供一个")

        # ── 1) 计算所有查询向量 ──
        query_vecs: List[List[float]] = []

        if query:
            query_vecs.append(embed_text(query))

        if image_data:
            try:
                from . import embedder as _emb
                query_vecs.append(_emb.embed_image_from_bytes(image_data, mime_type))
            except Exception as e:
                print(f"[mm_memory] 查询图片 embedding 失败: {e}")

        if not query_vecs:
            return []

        # ── 2) 从数据库加载候选记忆 ──
        sql = f"SELECT {_SELECT_COLS} FROM memories"
        conditions = []
        params: list = []

        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        rows = self._conn.execute(sql, params).fetchall()

        # ── 3) 多向量联合评分：取每条记忆与所有查询向量的最大相似度 ──
        scored: dict[str, tuple[float, KnowledgeItem]] = {}  # id → (best_score, item)

        for row in rows:
            item = KnowledgeItem.from_row(row)
            if not item.embedding:
                continue

            best_score = max(
                cosine_similarity(qv, item.embedding) for qv in query_vecs
            )

            if best_score >= threshold:
                scored[item.id] = (best_score, item)

        # ── 4) 取 top_k 初始结果 ──
        initial_hits = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)[:top_k]

        if not initial_hits:
            return []

        # ── 5) 关联扩展：收集命中项的 group_id，拉取同组所有记录 ──
        expanded_ids: set[str] = set()  # 记录通过 group 扩展进来的 id
        if expand_groups:
            hit_group_ids = set()
            for _id, (score, item) in initial_hits:
                if item.group_id:
                    hit_group_ids.add(item.group_id)

            if hit_group_ids:
                placeholders = ",".join("?" * len(hit_group_ids))
                expand_sql = (f"SELECT {_SELECT_COLS} FROM memories "
                              f"WHERE group_id IN ({placeholders})")
                expand_rows = self._conn.execute(expand_sql, list(hit_group_ids)).fetchall()

                for row in expand_rows:
                    exp_item = KnowledgeItem.from_row(row)
                    if exp_item.id in scored:
                        continue  # 已有，跳过
                    expanded_ids.add(exp_item.id)
                    if not exp_item.embedding:
                        # 扩展项即使没有 embedding 也纳入（如旧数据）
                        scored[exp_item.id] = (0.0, exp_item)
                    else:
                        # 计算扩展项自身的相似度
                        exp_score = max(
                            cosine_similarity(qv, exp_item.embedding) for qv in query_vecs
                        )
                        scored[exp_item.id] = (exp_score, exp_item)

        # ── 6) 组装最终结果 & Group 平均分过滤 ──
        final_results: List[SearchResult] = []
        for item_id, (score, item) in scored.items():
            final_results.append(SearchResult(
                item=item,
                score=score,
                match_reason=self._match_reason(score, item.embed_type),
            ))

        final_results.sort(key=lambda r: r.score, reverse=True)

        # Group 平均分过滤：所有项（含扩展项）均参与平均分计算
        from collections import defaultdict
        group_scores: dict[str, list[float]] = defaultdict(list)
        for r in final_results:
            group_scores[r.item.group_id].append(r.score)

        passing_groups = set()
        for gid, scores in group_scores.items():
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            if avg >= threshold:
                passing_groups.add(gid)

        final_results = [r for r in final_results if r.item.group_id in passing_groups]

        # ── 7) 按分数降序排列，直接返回所有通过筛选的 item ──
        final_results.sort(key=lambda r: r.score, reverse=True)
        return final_results

    @staticmethod
    def _match_reason(score: float, embed_type: str) -> str:
        """生成匹配说明"""
        type_label = {
            "knowledge": "知识匹配",
            "source_text": "原始文本匹配",
            "source_image": "原始图片匹配",
        }.get(embed_type, "匹配")
        return f"{type_label} (相似度 {score:.3f})"

    # ── 删除记忆 ─────────────────────────────────────────

    def forget(self, memory_id: str) -> bool:
        """删除一条记忆"""
        cursor = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def forget_group(self, group_id: str) -> int:
        """删除同一 group 的所有记忆及关联图片文件"""
        self.delete_image_file(group_id)
        cursor = self._conn.execute("DELETE FROM memories WHERE group_id = ?", (group_id,))
        self._conn.commit()
        return cursor.rowcount

    def forget_all(self) -> int:
        """清空所有记忆及图片文件（危险操作）"""
        # 清空 images 目录
        import shutil
        if os.path.isdir(self._images_dir):
            shutil.rmtree(self._images_dir)
            os.makedirs(self._images_dir, exist_ok=True)
        cursor = self._conn.execute("DELETE FROM memories")
        self._conn.commit()
        return cursor.rowcount

    # ── 列出记忆 ─────────────────────────────────────────

    def list_memories(self, limit: int = 50, offset: int = 0,
                      source_type: Optional[str] = None,
                      embed_type: Optional[str] = None) -> List[KnowledgeItem]:
        """列出记忆条目（不含 embedding 以节省内存）"""
        sql = f"SELECT {_SELECT_COLS_NO_EMBED} FROM memories"
        conditions = []
        params: list = []

        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if embed_type:
            conditions.append("embed_type = ?")
            params.append(embed_type)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(sql, params).fetchall()
        return [KnowledgeItem.from_row(row) for row in rows]

    def count(self, source_type: Optional[str] = None,
              embed_type: Optional[str] = None) -> int:
        """统计记忆数量"""
        sql = "SELECT COUNT(*) FROM memories"
        conditions = []
        params: list = []
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if embed_type:
            conditions.append("embed_type = ?")
            params.append(embed_type)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return self._conn.execute(sql, params).fetchone()[0]

    def get(self, memory_id: str) -> Optional[KnowledgeItem]:
        """获取单条记忆"""
        row = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return KnowledgeItem.from_row(row) if row else None

    def get_group(self, group_id: str) -> List[KnowledgeItem]:
        """获取同一 group 的所有记忆"""
        rows = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM memories WHERE group_id = ?", (group_id,)
        ).fetchall()
        return [KnowledgeItem.from_row(row) for row in rows]


    # ── 图片文件存储 ──────────────────────────────────────

    def store_image_file(self, group_id: str, mime_type: str, data: bytes) -> str:
        """将图片二进制数据存为文件，返回文件路径"""
        ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
        img_filename = f"{group_id}.{ext}"
        img_path = os.path.join(self._images_dir, img_filename)
        with open(img_path, "wb") as f:
            f.write(data)
        return img_path

    def get_image_path(self, group_id: str) -> Optional[str]:
        """根据 group_id 获取图片文件路径（从 source_path 列读取）"""
        row = self._conn.execute(
            "SELECT source_path FROM memories WHERE group_id = ? AND embed_type = 'source_image' LIMIT 1",
            (group_id,)
        ).fetchone()
        if row:
            path = row[0] or ""
            if path and os.path.exists(path):
                return path
        return None

    def get_image_data(self, group_id: str) -> Optional[dict]:
        """根据 group_id 读取图片文件数据（兼容旧接口）"""
        path = self.get_image_path(group_id)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            # 从扩展名推断 mime_type
            ext = os.path.splitext(path)[1].lstrip(".")
            mime_type = f"image/{ext}" if ext else "image/png"
            return {"path": path, "mime_type": mime_type, "data": data}
        return None

    def delete_image_file(self, group_id: str) -> bool:
        """删除 group 关联的图片文件"""
        path = self.get_image_path(group_id)
        if path and os.path.exists(path):
            os.remove(path)
            return True
        return False

    def image_count(self) -> int:
        """统计 images 目录中的图片文件数"""
        if os.path.isdir(self._images_dir):
            return len([f for f in os.listdir(self._images_dir)
                       if os.path.isfile(os.path.join(self._images_dir, f))])
        return 0


# ── 全局便捷实例 ─────────────────────────────────────────

_engine: Optional[MemoryEngine] = None


def get_engine(db_path: str = _DEFAULT_DB) -> MemoryEngine:
    """获取全局引擎实例（懒初始化）"""
    global _engine
    if _engine is None:
        _engine = MemoryEngine(db_path)
    return _engine