# 多模态记忆系统 (Multimodal Memory)

## 概述
基于语义 Embedding 的多模态记忆系统。支持文本/图片输入 → LLM 知识提取 → 多向量存储（原始文本/原始图片/提取知识分别 embedding，共享 group_id 关联）→ SQLite 存储 → 多向量联合检索 + 关联扩展 + 去重。图片存储到 images/ 目录，路径记录在 SQLite 中。

## 快速使用

```python
import sys
sys.path.insert(0, "/Users/xuekejun/CursorProjects/GenericAgent/memory/multimodal_memory")

from mm_memory import memorize, recall, forget, forget_group, get_group
from mm_memory import get_image_path_by_group, image_count, show_image

# 存入文本记忆（自动 LLM 提取 + 多模态 Embedding）
items = memorize(content="Python的GIL是全局解释器锁")
# → 返回 List[KnowledgeItem]，最多3条: source_text + knowledge，共享 group_id

# 存入图片记忆（传文件路径，自动复制到 images/ 目录 + 保存绝对路径）
items = memorize(image_path="/path/to/photo.jpg")
# → 复制文件到 images/ 目录、推断 mime_type、source_path 保存绝对路径

# 存入文本+图片记忆
items = memorize(content="架构说明", image_path="/path/to/photo.jpg")
# → 返回: source_text + source_image + knowledge

# 语义检索（文本）
results = recall("Python多线程", top_k=5, threshold=0.3)
for r in results:
    print(f"[{r.score:.3f}] [{r.item.embed_type}] {r.item.content[:50]}")

# 多模态联合检索（推荐：文件路径方式）
results = recall("界面布局", image_path="/path/to/screenshot.jpg")

# 多模态联合检索（bytes 方式也支持）
results = recall("界面布局", image_data=img_bytes, mime_type="image/jpeg")

# 按来源类型过滤
results = recall("查询", source_type="text")

# 禁用关联扩展
results = recall("查询", expand_groups=False)

# 删除
forget(items[0].id)              # 删除单条
forget_group(items[0].group_id)  # 删除整组关联记忆

# 查看关联组
group_items = get_group(items[0].group_id)

# 获取存储的图片文件路径
img_path = get_image_path_by_group(items[0].group_id)
if img_path:
    print(img_path)  # e.g. "/path/to/mm_memory/images/xxx.jpg"

# 直接显示图片（PIL）
show_image(group_id=items[0].group_id)  # 按 group_id 显示
show_image(image_path="/path/to/photo.jpg")  # 直接指定路径

# ★ 最佳实践：从 recall 结果直接获取图片路径并显示
# recall 返回的混合记忆中，embed_type="source_image" 的记录的 source_path 就是图片路径
results = recall("猫咪")
for r in results:
    if r.item.embed_type == "source_image" and r.item.source_path:
        show_image(image_path=r.item.source_path)  # 直接用 source_path，无需 get_image_path_by_group
        break
```

## API 参考

### 模块级函数（`from mm_memory import ...`）

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `memorize(content, image_path, context, auto_extract)` | content/image_path 至少一个 | `List[KnowledgeItem]` | 存入记忆，生成最多3条关联记录(source_text/source_image/knowledge)，共享group_id。传 image_path 文件路径，自动复制到 images/ 目录 + 保存绝对路径到 source_path |
| `memorize_raw(content, source_type, embed_type, group_id)` | content 必填 | `KnowledgeItem` | 直接存入，跳过 LLM 提取，支持指定 embed_type 和 group_id |
| `recall(query, image_data/image_path, mime_type, top_k, threshold, source_type, expand_groups)` | query/image_data/image_path 至少一个 | `List[SearchResult]` | 多向量联合检索 → group关联扩展 → 去重，按相似度降序。支持 image_path(文件路径) 或 image_data(bytes)，mime_type 自动推断。expand_groups 默认 True |
| `forget(memory_id)` | id 字符串 | `bool` | 删除单条记忆 |
| `forget_group(group_id)` | group_id 字符串 | `int` | 删除同组所有关联记忆及图片文件，返回删除数 |
| `get_group(group_id)` | group_id 字符串 | `List[KnowledgeItem]` | 获取同组所有关联记忆 |
| `forget_all()` | 无 | `int` | 清空所有记忆，返回删除数 |
| `list_memories(limit, offset, source_type, embed_type)` | 可选过滤 | `List[KnowledgeItem]` | 列出记忆（不含 embedding） |
| `count(source_type, embed_type)` | 可选过滤 | `int` | 统计数量 |
| `get(memory_id)` | id 字符串 | `Optional[KnowledgeItem]` | 获取单条记忆 |
| `unique_images(results)` | SearchResult 列表 | `List[SearchResult]` | 按 group_id 去重，每组保留最高分项 |

### 图片文件操作

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `get_image_path_by_group(group_id)` | group_id 字符串 | `str` 或 `None` | 按 group_id 获取关联图片的文件路径 |
| `image_count()` | 无 | `int` | 统计已存储的图片文件数量 |
| `show_image(group_id, image_path)` | group_id 或 image_path 二选一 | `bool` | 用 PIL 显示图片 |

### 底层工具

| 函数 | 说明 |
|------|------|
| `embed_text(text)` | 计算文本 Embedding |
| `embed_image(image_path)` | 计算图片 Embedding（文件路径方式） |
| `embed_image_from_bytes(data, mime_type)` | 计算图片 Embedding（bytes 方式） |
| `embed_texts(texts)` | 批量计算文本 Embedding |
| `cosine_similarity(a, b)` | 计算余弦相似度 |
| `extract_from_text(text, context)` | LLM 提取文本知识 |
| `extract_from_image(image_path, context)` | LLM 提取图片知识（文件路径方式） |
| `extract_from_image_bytes(data, mime_type, context)` | LLM 提取图片知识（bytes 方式） |
| `extract_from_image_and_text(image_path, text, context)` | LLM 提取图片+文本混合知识 |

## 数据模型

### KnowledgeItem
```python
@dataclass
class KnowledgeItem:
    id: str              # UUID (自动生成)
    content: str         # 原始/提取后内容
    source_type: str     # "text" | "image" | "mixed"
    source_path: str     # 图片文件存储路径（images/ 目录下）
    embedding: List[float]  # 向量
    created_at: float    # 时间戳
    group_id: str        # 关联分组ID（同次memorize的记录共享，默认=id）
    embed_type: str      # "source_text" | "source_image" | "knowledge"
```

### SearchResult
```python
@dataclass
class SearchResult:
    item: KnowledgeItem  # 匹配的记忆条目
    score: float         # 余弦相似度 (0~1)
    match_reason: str    # 匹配说明
```
> **访问方式**：`SearchResult` 支持 `r["key"]` 和 `r.get("key")` 字典式访问（会自动代理到 `r.item`），但推荐直接用 `r.item.content`、`r.item.embed_type` 等属性访问，更清晰。

## 配置

环境变量（通过 `my_key/oai_config2.json` 自动加载）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| Embedding API Base | 嵌入服务地址 | `api.bianxie.ai/v1` |
| Embedding Model | 嵌入模型 | `gemini-embedding-2-preview` |
| Chat API Base | 知识提取服务 | `api.bianxie.ai/v1` |
| Chat Model | 提取模型 | `claude-opus-4-6`（文本与图片统一） |

## 目录结构
```
memory/multimodal_memory/
├── mm_memory/
│   ├── __init__.py      # 公开接口（模块级函数 + 模型导出 + 底层工具）
│   ├── models.py        # 数据模型（KnowledgeItem/SearchResult）
│   ├── embedder.py      # Embedding 计算（文本/图片/bytes/批量）
│   ├── extractor.py      # LLM 知识提取
│   └── engine.py         # 核心引擎（SQLite + 检索 + 文件存储）
├── mm_data.db           # SQLite 数据库（自动创建）
├── images/              # 图片文件目录（自动创建）
└── MEMORY.md           # 本文档
```
