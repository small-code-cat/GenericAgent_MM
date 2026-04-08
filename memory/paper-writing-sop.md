# 论文写作与绘图 SOP

> 从宏观叙事到微观用词、从章节结构到图表规范的全链路操作手册。

---

## 1. 写作总则

### 叙事框架

每段遵循三拍节奏：**What → Why → So What**
- What：我们做了什么 / 观察到什么
- Why：为什么这很重要 / 为什么现有方法不够
- So What：这意味着什么 / 读者应如何行动

### 审稿人行为模型

审稿人只花 **30 分钟**，阅读顺序：
1. 摘要 → 2. 结论 → 3. 图表 → 4. 方法细节

**启示**：摘要和结论必须自包含；图表 caption 必须独立可读；方法部分先给直觉再给公式。

### 写作风格核心原则（Gopen & Swan）

| 原则 | 要点 |
|------|------|
| 主语紧跟动词 | 主谓间不超过 7-8 词 |
| 旧→新信息流 | 句首放已知，句尾放新信息 |
| Stress Position | 句末放最重要的概念 |
| 主题一致性 | 同一段落主语保持一致 |
| 一段一主题 | 段首句即为该段论点 |

---

## 2. 各章节写作指南

### Abstract（5 句公式）

| 句序 | 功能 | 示例开头 |
|------|------|----------|
| 1 | 背景/领域重要性 | "Large language models have..." |
| 2 | 问题/现有不足 | "However, existing methods..." |
| 3 | 我们的方法 | "We propose X, which..." |
| 4 | 关键结果（带数字） | "X achieves 92.1% on..." |
| 5 | 更广泛意义 | "Our findings suggest..." |

**检查**：删掉第一句，如果它能放在任何 ML 论文前面，就删掉它。

### Introduction（4 段公式）

1. **领域重要性**：为什么这个问题值得关注（2-3 句）
2. **现有方法不足**：具体指出 gap，不要泛泛而谈
3. **我们的方案**：一句话概括核心思路
4. **贡献列表**：用 itemize，3-4 条，每条一句话

**红线**：Introduction 不超过 1.5 页。超了就把背景拆到 Related Work。

### Related Work

- 按**主题分组**，不要按时间线罗列
- 每组结尾点明与本文的区别："Unlike X, our approach..."
- 不要贬低前人工作，用 "differs from" 而非 "fails to"

### Method

- **先直觉后公式**：每个公式前必须有一句自然语言解释
- **符号表**：首次出现时定义，全文一致
- 复杂方法配一张 overview figure
- 分小节，每节解决一个子问题

### Experiments

- 每个实验前写明 claim："This experiment tests whether..."
- **必须包含**：
  - Error bars（标明是 std dev 还是 std error）
  - 运行次数
  - 统计检验（如比较方法间差异）
- Ablation 要逐个移除组件，证明每个都有贡献

### Discussion & Conclusion

- Discussion：诚实讨论 limitations，主动提比审稿人先提
- Conclusion：不要重复摘要，强调 implications 和 future work
- 最后一句面向未来，不要以 limitation 结尾

---

## 3. 微观写作技巧

### 禁用词表

| 禁用 | 替代 |
|------|------|
| novel | （直接删除，让方法本身说话） |
| utilize | use |
| leverage | use / build on |
| in order to | to |
| it is worth noting that | （直接写要说的） |
| a number of | several / 具体数字 |

### 句式规范

- **主动语态优先**："We train the model" 而非 "The model is trained"
- **避免模糊代词**："This" 后必须跟名词（"This approach" 而非 "This"）
- **数字一致性**：同一表格内小数位数对齐
- **时态**：方法用现在时，实验结果用过去时

---

## 4. 表格规范

```latex
\usepackage{booktabs}
\begin{tabular}{lcc}
\toprule
Method & Accuracy ↑ & Latency ↓ \\
\midrule
Baseline & 85.2 & 45ms \\
\textbf{Ours} & \textbf{92.1} & 38ms \\
\bottomrule
\end{tabular}
```

**规则**：
- 加粗每列最优值
- 方向符号标注（↑ 越高越好，↓ 越低越好）
- 数值列右对齐，小数位统一
- 用 `booktabs`（`\toprule/\midrule/\bottomrule`），禁用竖线

---

## 5. 学术绘图指南

### 5.1 概念图 / 架构图（Gemini 生成）

适用：系统架构、流程图、方法 overview 等无数值轴的图。

**4 种视觉风格**：

| 风格 | 特点 | 适用场景 |
|------|------|----------|
| A. Clean Technical | 白底、圆角矩形、蓝灰色系 | 通用架构图 |
| B. Warm Gradient | 暖色渐变、柔和阴影 | Pipeline/流程图 |
| C. Dark Sophisticated | 深色背景、霓虹高亮 | 高端展示、Poster |
| D. Hand-drawn Sketch | 手绘风、铅笔线条 | Workshop/博客 |

**Prompt 6 段结构**（缺一不可）：
1. FRAMING — 风格 + 会议 + 形容词
2. VISUAL STYLE — 完整风格描述块
3. COLOR PALETTE — 精确 hex 色值
4. LAYOUT — 每个组件的文字和空间位置
5. CONNECTIONS — 每条箭头的起止和样式
6. CONSTRAINTS — 明确禁止项

**关键规则**：
- 每次生成 3 张，挑最好的
- 所有标签必须在 prompt 中逐字拼出（Gemini 会拼错）
- 输出 PNG（AI 生成图无法矢量化）

### 5.2 数据图（matplotlib/seaborn）

适用：所有含数值轴、定量比较的图。

**图表选型**：

| 数据模式 | 图表类型 |
|----------|----------|
| 随时间/步数变化 | 折线图（训练曲线、scaling law） |
| 类别比较 | 分组柱状图（模型对比、ablation） |
| 分布 | 小提琴图 / 箱线图 |
| 相关性 | 散点图 |
| 值矩阵 | 热力图（attention、混淆矩阵） |
| 多方法单指标排名 | 水平柱状图（排行榜风格） |

**出版级样式模板**：

```python
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 8.5,
    "legend.frameon": False,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.15,
})

# 配色（色盲安全）
COLORS = ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51",
          "#0072B2", "#56B4E9", "#8C8C8C"]
OUR_COLOR = "#E76F51"       # 珊瑚色，突出"我们的方法"
BASELINE_COLOR = "#B0BEC5"  # 冷灰，基线退后

# 会议尺寸
FIG_SINGLE = (3.25, 2.5)   # 单栏
FIG_FULL = (6.75, 2.8)     # 双栏
```

**通用规则**：
- 矢量输出（PDF）用于 LaTeX，PNG（300 DPI）仅作备用
- "我们的方法"用醒目色，基线用灰色
- 不同方法同时用不同颜色 + 不同 marker/线型（兼顾灰度打印）
- 图内不加标题，由 caption 承担
- caption 必须自包含，不依赖正文即可理解
- 脚本保存为 `figures/gen_fig_<name>.py`，确保可复现

### 5.3 会议图片尺寸速查

| 会议 | 单栏宽 | 全宽 | 字体 |
|------|--------|------|------|
| NeurIPS | 5.5 in | 5.5 in | Times |
| ICML | 3.25 in | 6.75 in | Times |
| ICLR | 5.5 in | 5.5 in | Times |
| ACL | 3.3 in | 6.8 in | Times |
| AAAI | 3.3 in | 7.0 in | Times |

---

## 6. 引用规范

**核心原则：禁止凭记忆生成 BibTeX。**

引用工作流：
1. **搜索**：通过 Semantic Scholar API 查找论文
2. **交叉验证**：至少在两个源（Semantic Scholar + CrossRef/arXiv）确认存在
3. **获取 BibTeX**：通过 DOI 程序化获取（`https://doi.org/{doi}`, Accept: `application/x-bibtex`）
4. **验证 claim**：确认被引论文确实支持你的引用语境
5. **失败处理**：无法验证的标记 `[CITATION NEEDED]`，明确告知作者

---

## 7. 会议要求速查

| 会议 | 页数限制 | 关键特殊要求 |
|------|----------|-------------|
| NeurIPS | 正文 9 页 | 必须提交 checklist |
| ICML | 正文 8 页 | 引用不计入页数 |
| ICLR | 正文 10 页 | OpenReview 双盲 |
| ACL/EMNLP | 长文 8 / 短文 4 | 必须有 Limitations 节 |
| AAAI | 正文 7 页 + 1 页引用 | 必须有 Ethics Statement |
| OSDI/NSDI | 正文 12 页 | 必须有 artifact evaluation |

**转投 checklist**：换模板 → 调页数 → 检查特殊必需节 → 重新编译验证。