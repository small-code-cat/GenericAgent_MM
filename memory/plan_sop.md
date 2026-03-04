# Plan Mode SOP

## 1. 分类：识别任务结构
分析子任务间关系，选择匹配的结构：

- **Sequential** — 步骤间有输入输出依赖 (部署/ETL/构建)
- **MapReduce** — 多独立维度，各自深入后汇总 (5P/SWOT/多文件审查)
- **Branch** — 结果不确定，按条件选路径 (调试/探测/方案选择)
- **Loop** — 重复直到满足条件 (优化/翻页/迭代修改)
- **DAG** — 混合依赖，部分可并行 (项目开发)

可嵌套：大结构某步内部用另一种结构

## 2. 分解模板

**Sequential:**  `[ ] A → [ ] B → [ ] C`

**MapReduce:**
```
MAP [子流程: 读现状→分析→输出]:
[ ] 维度1: ...
[ ] 维度2: ...
REDUCE:
[ ] 汇总 → 终稿
```

**Branch:**  `[ ] 尝试X → 成功:[ ]Y / 失败:[ ]Z`

**Loop:**  `[ ] LOOP(max=N): 执行→检查→调整`

**DAG:**  `[ ] A → [ ]{B,C}并行 → [ ]D汇聚`

## 3. 写入 checkpoint

=== PLAN (结构类型) ===
...
=== PLAN RULES ===
- 每完成/跳过一步，重新 update working checkpoint
- 任何 checkpoint update 必须保留 PLAN
================