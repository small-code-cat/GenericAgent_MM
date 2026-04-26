# Survey SOP（文献调研）

> 独立模块，可单独触发，也可作为论文全流程的第一步。

## 输出位置
- 独立模式（默认）：`temp/survey/`
- 项目模式（用户提供根目录）：`{project_root}/survey/`

## 触发关键词
调研 / survey / 文献 / literature / 论文搜索

## 流程

### 1. 明确范围
- 与用户确认：研究主题、关键词（英文）、时间范围
- 🔴 **仅认可 8 大 AI 顶会**：AAAI, ACL, CVPR, EMNLP, ICLR, NeurIPS, ICML, ICCV
- 近半年论文（尚未被顶会收录）可从 arXiv 检索，需标注为 preprint
- 无明确指定时默认近 3 年，经典论文可追溯更早

### 2. 搜索文献
- 🔴 **主搜索源**：`https://papers.cool`（用 `web_scan` / `web_execute_js` 操作）
- **补充源**：arXiv（仅限近半年内尚未被顶会收录的论文）
- 🔴 **禁止使用** Google Scholar / Semantic Scholar 作为搜索源
- 每篇记录：标题、作者、年份、venue（必须为8大顶会之一或标注arXiv preprint）、核心贡献、URL
- 搜索策略：主关键词 → 同义词/变体 → 引用链追踪（被引 & 参考文献）
- **筛选规则**：搜索结果中非 8 大顶会的论文直接跳过（近半年 arXiv preprint 除外）

### 3. 分类整理
- 按主题/方法分组，存入 `survey/papers.md`（表格形式）
- 模板：
```markdown
| # | 标题 | 作者 | 年份 | Venue | 核心贡献 | URL |
|---|------|------|------|-------|---------|-----|
```

### 4. 生成综述
- 识别 3-5 个研究主线（research threads）
- 每条主线：发展脉络 → 当前 SOTA → 局限性
- 输出 `survey/literature_review.md`

## 输出结构
```
survey/
├── papers.md              # 论文清单（表格）
├── literature_review.md   # 综述分析
```

## 🔴 避坑
- **禁止编造论文**——所有引用必须通过搜索验证存在
- **禁信摘要**——关键数据（数值/方法细节）必须进详情页核实
- **Venue 必须核实**——papers.cool 搜索结果需确认论文确实发表于 8 大顶会（AAAI/ACL/CVPR/EMNLP/ICLR/NeurIPS/ICML/ICCV），Workshop 论文不算
- **arXiv 仅限近半年**——超过半年仍为 preprint 的论文不收录
- 综述不是论文列表——要分析脉络和趋势

## 🔧 papers.cool 自动化要点
- **搜索URL**：`papers.cool/{branch}/search?highlight=1&query={keywords}`，branch=`arxiv`(预印本) 或 `venue`(会议论文)
- **⚠ 禁用Go按钮点击**（内部用window.open会被拦截），必须用 `location.href` 直接导航
- **venue分支**自带会议标签，`.venue`字段格式：`Subject: VENUE.YEAR - Type`，可直接筛选8大顶会
- **结果选择器**：`.panel.paper`(容器)、`.title-link`(标题)、`.authors`(作者)、`.summary`(摘要)、`.venue`(会议)
- **提取JS模板**：遍历`.panel.paper`提取id/title/authors/summary/venue，JSON.stringify后save_to_file
- **⚠ venue字段常为空**：venue分支的`.venue`选择器经常无内容，需从paper ID解析venue：`YYYY.acl-long.NUM@ACL`→ACL、`YYYY.findings-emnlp.NUM@EMNLP`→EMNLP(findings也算)、`@CVPRYYYY@CVF`→CVPR、`ID@OpenReview`→需访问详情页确认
- **OpenReview论文**：venue搜索结果中venue永远为空，必须访问`papers.cool/venue/{openreview_id}@OpenReview`详情页确认是否属于8大顶会
- **Authors字段清洗**：提取结果含"Authors:"前缀和换行符，生成markdown表格前必须清理（去前缀+换行→空格）