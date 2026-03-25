# 多模态记忆系统 SOP

> **定位**：Agent 使用多模态记忆系统（存储/检索文本+图片）的操作指南
> **触发**：用户要求"记住/存储/回忆/查找"信息，或 Agent 需持久化知识时

---

## 0. 快速开始

```python
import sys; sys.path.append("/Users/xuekejun/CursorProjects/GenericAgent_MM/memory/multimodal_memory")
from mm_memory import memorize, recall
```
> ⚠️ **必须用绝对路径**。cwd通常是temp/，相对路径`"memory/multimodal_memory"`会指向不存在的`temp/memory/...`导致import失败。

- **存**：`memorize("要记住的内容")` → 返回 `str`（摘要）
- **取**：`recall("查询关键词")` → 返回 `List[SearchResult]`
- 内部自动查重（相似度≥0.8 跳过），无需手动去重

---

## 1. 核心规则（必读）

| 规则 | 说明 |
|------|------|
| ⭐ 首选接口 | **只用 `memorize` + `recall`**，其他函数仅高级场景使用 |
| 🚫 禁止 base64 | 图片一律传文件路径，禁止 base64 编码 |
| 🚫 禁止批量循环 | 不要循环调用 memorize，一次调用处理一组图文 |
| ⚠️ 图片自动探测 | 未传 image_path 时，自动扫描 `temp/uploads/` 最近60秒内的图片 |
| ⚠️ 返回值是字符串 | `memorize()` 返回 `str`（人类可读摘要），不是列表 |
| 🔴 recall失败必重试 | recall报错/返回空时，先检查路径和参数，必须重试，禁止直接放弃跳过 |
| 🔴 禁止幻觉结果 | 必须等待真实tool_result返回，禁止自行编造recall/memorize的执行结果 |
| 🔴 展示图片禁用markdown | recall到图片后，必须用 `code_run` 执行 `subprocess.Popen(["open", path])` 弹出查看器，**严禁**用 `![](path)` 或浏览器打开。详见场景C |

---

## 2. 场景 A：存储记忆（memorize）

### 签名
```python
def memorize(content="", image_path=None, context="", auto_extract=True, **kwargs) -> str
```

### 参数别名
- `content` 的别名：`text` / `desc` / `description`
- `image_path` 的别名：`image_file` / `img_path`

### 场景示例

**纯文本**
```python
result = memorize("Python的GIL是全局解释器锁，限制多线程并行")
print(result)  # "[记忆已存储] group=xxx, 共2条记录: ..."
```

**纯图片**（用户上传图片后）
```python
result = memorize(image_path="/path/to/screenshot.png")
# 自动：复制到 images/ + LLM提取图片知识 + embedding
```

**图文混合**
```python
result = memorize("这是系统架构图", image_path="/path/to/arch.png")
# 生成最多3条记录：source_text + source_image + knowledge
```

**无需手动传图片路径**：用户刚上传图片时，直接 `memorize("描述")` 即可，系统自动探测 `temp/uploads/` 中最新文件。

### 查重机制
- 纯文本：文本最高分≥0.8 → 跳过
- 纯图片：图片最高分≥0.8 → 跳过
- 图文混合：文本和图片两个维度都≥0.8 → 才跳过
- 跳过时返回：`"[记忆跳过] 已存在相似记忆(group=xxx, 相似度=0.85)，无需重复存储。"`

---

## 3. 场景 B：检索记忆（recall）

### 签名
```python
def recall(query="", image_data=None, mime_type="image/png",
           top_k=5, threshold=0.35, source_type=None,
           expand_groups=True, **kwargs) -> List[SearchResult]
```

### 场景示例

**文本检索**
```python
results = recall("Python多线程为什么慢")
for r in results:
    print(f"[{r.score:.2f}] {r.content[:100]}")
    if r.source_path:  # 有关联图片
        print(f"  图片: {r.source_path}")
```

**图片检索**（传文件路径，自动读取）
```python
results = recall(image_path="/path/to/query.png")
```

**图文联合检索**
```python
results = recall("架构图", image_path="/path/to/ref.png")
```

### SearchResult 字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | str | 记忆内容文本 |
| `score` | float | 相似度分数 |
| `source_type` | str | `"text"` / `"image"` |
| `embed_type` | str | `"source_text"` / `"source_image"` / `"knowledge"` |
| `group_id` | str | 同组记忆的关联ID |
| `source_path` | str | 图片文件路径（仅source_image记录有值） |
| `created_at` | float | 创建时间戳 |

### 检索调优
| 参数 | 首选值 | 说明 |
|------|--------|------|
| `top_k` | 5 | 返回条数，信息不足时可增到10-20 |
| `threshold` | 0.35 | 最低分数，精确查找可提高到0.5 |
| `expand_groups` | True | 自动展开同组记忆（获取关联图片/知识） |
| `source_type` | None | 过滤：`"text"` 仅文本 / `"image"` 仅图片 |

---

## 4. 场景 C：向用户展示记忆中的图片

### 正确流程
```python
import shutil, os

# 1. recall 获取图片路径
results = recall("查询词")
img_path = None
for r in results:
    if r.source_path:  # source_image 类型的记录才有图片路径
        img_path = r.source_path
        break

# 2. 复制到 temp/uploads/ 以便系统可访问
if img_path:
    dest = os.path.join("/Users/xuekejun/CursorProjects/GenericAgent_MM/temp/uploads", os.path.basename(img_path))
    shutil.copy2(img_path, dest)
    # 3. 用系统查看器打开
    import subprocess
    subprocess.Popen(["open", dest])  # macOS
    print(f"已打开图片: {dest}")
```

### 🔴 禁止事项
| 禁止 | 原因 |
|------|------|
| `![alt](local_path)` Markdown图片语法 | 聊天界面**无法渲染本地文件路径**，用户看到的只是一行文字 |
| `show_image()` 函数 | 已废弃 |
| 直接输出 source_path 当作展示 | 路径文本≠图片展示 |
| `from IPython.display import Image` | 环境无IPython，必报 `ModuleNotFoundError` |

### ✅ 最佳实践
1. **必须通过 code_run 执行代码**调用 `subprocess.Popen(["open", path])` 弹出图片，用户期望的是屏幕上直接弹出图片查看器
2. 🔴 **核心易错点**：不要只在对话文本中"描述"怎么打开图片，必须实际执行代码让图片弹出来
3. 可同时用文字简要描述图片内容作为补充（如"这是你的深灰色 Model 3 的车尾照"）

---

## 5. 高级功能（非常规场景）

以下函数仍可导入使用，但**日常场景只用 memorize + recall**：

| 函数 | 用途 | 返回值 |
|------|------|--------|
| `memorize_raw(content, ...)` | 跳过LLM直接存储（仅embedding） | `KnowledgeItem` |
| `forget(item_id)` | 删除单条记忆 | `bool` |
| `forget_group(group_id)` | 删除整组记忆 | `int`（删除条数） |
| `get_group(group_id)` | 获取整组记忆 | `List[KnowledgeItem]` |
| `list_memories(limit)` | 列出最近记忆 | `List[KnowledgeItem]` |
| `get_image_path_by_group(group_id)` | 获取组内图片路径 | `str\|None` |
| `image_count()` | 图片记忆总数 | `int` |
| `unique_images()` | 去重图片路径列表 | `List[str]` |

> ⚠️ 注意：`memorize()` 返回 `str` 而非对象，无法直接获取 `group_id`。
> 如需 group_id，从返回字符串中解析：`group=xxx` 部分，或使用 `list_memories()` 查询。

---

## 6. 数据模型

### KnowledgeItem（存储单元）
每次 memorize 调用生成1-3条 KnowledgeItem，共享同一 `group_id`：
- `source_text`：原始文本
- `source_image`：图片描述（LLM生成）
- `knowledge`：提取的结构化知识

### 记忆生命周期
```
memorize("文本", image_path="图片")
  → LLM提取知识 → embedding → 存入SQLite
  → 返回 str 摘要

recall("查询")
  → query embedding → 余弦相似度 → 展开同组 → 返回 List[SearchResult]
```

---

## 7. 环境配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| Embedding API Base | 嵌入服务地址 | `api.bianxie.ai/v1` |
| Embedding Model | 嵌入模型 | `gemini-embedding-2-preview` |
| Chat API Base | 知识提取服务 | `api.bianxie.ai/v1` |
| Chat Model | 提取模型 | `claude-opus-4-6`（文本与图片统一） |

### 目录结构
```
memory/multimodal_memory/
├── mm_memory/
│   ├── __init__.py      # 公开接口（memorize, recall 等）
│   ├── models.py        # 数据模型
│   ├── embedder.py      # Embedding 计算
│   ├── extractor.py     # LLM 知识提取
│   └── engine.py        # 核心引擎（SQLite + 检索 + 文件存储）
├── mm_data.db           # SQLite 数据库（自动创建）
├── images/              # 图片文件目录（自动创建）
└── MEMORY.md            # 本文档
```