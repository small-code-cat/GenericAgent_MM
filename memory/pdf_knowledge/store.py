"""
store.py – PDF 知识库的 SQLite 存储层
管理文档元数据、页面图片路径和 embedding 向量
"""

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import List, Optional

# ── 路径 ──────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_BASE_DIR, "pdf_knowledge.db")


# ── 数据模型 ──────────────────────────────────────────

@dataclass
class PDFDocument:
    pdf_id: str
    filename: str
    page_count: int
    created_at: float = 0.0
    thumbnail_path: str = ""


@dataclass
class PDFPage:
    pdf_id: str
    page_num: int
    image_path: str
    embedding: List[float] = field(default_factory=list)


@dataclass
class SearchResult:
    pdf_id: str
    page_num: int
    image_path: str
    score: float
    filename: str = ""


# ── 数据库初始化 ──────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db():
    """创建表结构（幂等）"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pdf_documents (
            pdf_id       TEXT PRIMARY KEY,
            filename     TEXT NOT NULL,
            page_count   INTEGER NOT NULL DEFAULT 0,
            thumbnail    TEXT DEFAULT '',
            created_at   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pdf_pages (
            pdf_id       TEXT NOT NULL,
            page_num     INTEGER NOT NULL,
            image_path   TEXT NOT NULL,
            embedding    TEXT DEFAULT '',
            PRIMARY KEY (pdf_id, page_num),
            FOREIGN KEY (pdf_id) REFERENCES pdf_documents(pdf_id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


# 模块加载时自动初始化
_init_db()


# ── 文档操作 ──────────────────────────────────────────

def save_document(pdf_id: str, filename: str, page_count: int,
                  thumbnail_path: str = "") -> PDFDocument:
    """保存 PDF 文档元数据"""
    now = time.time()
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO pdf_documents "
        "(pdf_id, filename, page_count, thumbnail, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (pdf_id, filename, page_count, thumbnail_path, now),
    )
    conn.commit()
    conn.close()
    return PDFDocument(pdf_id, filename, page_count, now, thumbnail_path)


def get_document(pdf_id: str) -> Optional[PDFDocument]:
    """获取文档元数据"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT pdf_id, filename, page_count, created_at, thumbnail "
        "FROM pdf_documents WHERE pdf_id = ?",
        (pdf_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return PDFDocument(
        pdf_id=row[0], filename=row[1], page_count=row[2],
        created_at=row[3], thumbnail_path=row[4] or "",
    )


def list_documents() -> List[PDFDocument]:
    """列出所有已入库的文档"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT pdf_id, filename, page_count, created_at, thumbnail "
        "FROM pdf_documents ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [
        PDFDocument(r[0], r[1], r[2], r[3], r[4] or "")
        for r in rows
    ]


def delete_document(pdf_id: str):
    """删除文档及其所有页面（级联删除）"""
    conn = _get_conn()
    conn.execute("DELETE FROM pdf_documents WHERE pdf_id = ?", (pdf_id,))
    conn.commit()
    conn.close()


# ── 页面操作 ──────────────────────────────────────────

def save_page(pdf_id: str, page_num: int, image_path: str,
              embedding: List[float] = None):
    """保存单页信息和 embedding"""
    emb_json = json.dumps(embedding) if embedding else ""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO pdf_pages "
        "(pdf_id, page_num, image_path, embedding) "
        "VALUES (?, ?, ?, ?)",
        (pdf_id, page_num, image_path, emb_json),
    )
    conn.commit()
    conn.close()


def save_pages_batch(pages: List[PDFPage]):
    """批量保存页面"""
    conn = _get_conn()
    for p in pages:
        emb_json = json.dumps(p.embedding) if p.embedding else ""
        conn.execute(
            "INSERT OR REPLACE INTO pdf_pages "
            "(pdf_id, page_num, image_path, embedding) "
            "VALUES (?, ?, ?, ?)",
            (p.pdf_id, p.page_num, p.image_path, emb_json),
        )
    conn.commit()
    conn.close()


def get_pages(pdf_id: str) -> List[PDFPage]:
    """获取某文档的所有页面"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT pdf_id, page_num, image_path, embedding "
        "FROM pdf_pages WHERE pdf_id = ? ORDER BY page_num",
        (pdf_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        emb = json.loads(r[3]) if r[3] else []
        result.append(PDFPage(r[0], r[1], r[2], emb))
    return result


def get_all_pages_with_embeddings() -> List[PDFPage]:
    """获取所有有 embedding 的页面（用于全局搜索）"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT p.pdf_id, p.page_num, p.image_path, p.embedding "
        "FROM pdf_pages p "
        "WHERE p.embedding != '' "
        "ORDER BY p.pdf_id, p.page_num"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        emb = json.loads(r[3]) if r[3] else []
        if emb:
            result.append(PDFPage(r[0], r[1], r[2], emb))
    return result