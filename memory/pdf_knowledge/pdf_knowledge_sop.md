# PDF知识库检索SOP (pdf_knowledge_sop)

## 触发条件
用户提到「知识库」「查文档」「查PDF」或要求从已入库文档中查找信息时触发。

## 检索-回答流程

### Step 1: 检索（code_run执行Python）, 只检索一次
```python
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))  # 项目根目录
from memory.pdf_knowledge.searcher import search_by_text

results = search_by_text("用户的问题", top_k=3)
for r in results:
    print(f"[{r.filename}] 第{r.page_num}页 (相关度:{r.score:.3f})")
    print(r.image_path)  # 🔴必须print路径，agent_loop会自动内联为图片
```

- `search_by_text(query, top_k=3, threshold=0.0, pdf_id="")` → `List[SearchResult]`
- `search_by_image(image_path, top_k=3, ...)` → 用图片检索，接口同上
- SearchResult字段：`pdf_id, page_num, image_path, score, filename`
- 可用 `pdf_id=""` 限定在某个文档内搜索

### Step 2: 查看列表（可选，用户问"有哪些文档"时）
```python
from memory.pdf_knowledge.store import list_documents
for doc in list_documents():
    print(f"{doc.filename} ({doc.page_count}页) id={doc.pdf_id}")
```

### Step 3: 回答
code_run输出中的图片路径会被系统自动转为内联图片。直接根据看到的页面图片内容回答用户问题。

## ⚠️ 关键约束
1. **必须print image_path**：这是图片内联的触发机制，漏掉则LLM看不到页面
2. **query要精炼**：提取用户问题的核心关键词作为检索query，不要直接用长句
3. **top_k按需调整**：简单问题top_k=3，复杂/模糊问题可增大到5
4. **无结果时**：告知用户知识库中未找到相关内容，建议检查是否已入库