"""多模态记忆系统 — 数据模型"""
from __future__ import annotations
import json, time, uuid
from dataclasses import dataclass, field
from typing import List, Optional

_SENTINEL = object()  # 用于区分"属性不存在"和"属性值为None"


@dataclass
class KnowledgeItem:
    """一条知识记忆
    
    embed_type 取值:
      - "knowledge"     : LLM 提取的知识文本（默认，兼容旧数据）
      - "source_text"   : 原始输入文本的 embedding
      - "source_image"  : 原始输入图片的 embedding
    
    group_id: 同一次 memorize() 调用产生的多条记录共享同一 group_id，
              用于检索后的关联扩展。
    """
    id: str = ""
    content: str = ""                    # 知识内容（source_text=原文, source_image=图片描述, knowledge=综合理解）
    source_type: str = "text"            # text / image / mixed
    embedding: List[float] = field(default_factory=list)
    created_at: float = 0.0
    source_path: str = ""                # 仅 source_image 记录存图片路径
    group_id: str = ""                   # 同组关联 ID
    embed_type: str = "knowledge"        # knowledge / source_text / source_image

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = time.time()
        if not self.group_id:
            self.group_id = self.id       # 默认 group_id = 自身 id

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "source_type": self.source_type,
            "embedding": self.embedding,
            "created_at": self.created_at,
            "source_path": self.source_path,
            "group_id": self.group_id,
            "embed_type": self.embed_type,
        }

    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeItem":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_row(cls, row: tuple) -> "KnowledgeItem":
        """从 SQLite 行构造
        
        列顺序: id, content, source_type, source_path,
                embedding_json, created_at, group_id, embed_type
        """
        item_id = row[0]
        item = cls(
            id=item_id,
            content=row[1],
            source_type=row[2],
            source_path=row[3] or "",
            embedding=json.loads(row[4]) if row[4] else [],
            created_at=row[5],
            group_id=row[6] if len(row) > 6 and row[6] else item_id,
            embed_type=row[7] if len(row) > 7 and row[7] else "knowledge",
        )
        return item


@dataclass
class SearchResult:
    """语义检索结果 — 只暴露 score / content / source_path"""
    item: KnowledgeItem
    score: float = 0.0           # 余弦相似度
    match_reason: str = ""       # 匹配说明（内部调试用）

    # ── 三个核心只读属性 ──────────────────────────────
    @property
    def content(self) -> str:
        return self.item.content

    @property
    def source_path(self) -> str:
        return self.item.source_path

    def __getattr__(self, name: str):
        # 代理未知属性到 item（dataclass 自身字段不会走这里）
        try:
            return getattr(self.item, name)
        except AttributeError:
            raise AttributeError(f"'SearchResult' object has no attribute '{name}'")

    def __getitem__(self, key: str):
        # 先查自身属性，再代理到 item
        try:
            return getattr(self, key)
        except AttributeError:
            return getattr(self.item, key)

    def get(self, key: str, default=None):
        # 先查自身属性，再代理到 item
        val = getattr(self, key, _SENTINEL)
        if val is not _SENTINEL:
            return val
        return getattr(self.item, key, default)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "content": self.content,
            "source_path": self.source_path,
        }

    def __repr__(self):
        parts = [f"score={self.score:.3f}"]
        if self.source_path:
            parts.append(f"image={self.source_path!r}")
        else:
            parts.append(f"content={self.content[:60]!r}")
        return f"SearchResult({', '.join(parts)})"


# ── 智能眼镜场景：以用户为中心的语义实体 ─────────────────
