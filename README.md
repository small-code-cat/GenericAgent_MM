

[English](#english) | [中文](#chinese)

---



## 🌟 Overview

**GenericAgent_MM** is a secondary development based on [GenericAgent](https://github.com/lsdefine/GenericAgent), adding **multimodal memory** capabilities. On top of GenericAgent's minimal self-evolving agent framework (~3,300 lines of core code, 7 atomic tools + 92-line Agent Loop for full system-level control), GenericAgent_MM introduces a persistent multimodal memory system — the agent can **memorize and recall both text and images** via semantic vector search, progressively building a rich, personalized understanding of the user (preferences, photos, personal info, etc.). The longer you interact, the more it knows you.

> 🔗 Original project: [https://github.com/lsdefine/GenericAgent](https://github.com/lsdefine/GenericAgent)

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/small-code-cat/GenericAgent_MM.git
cd GenericAgent_MM

# 2. Install dependencies
pip install streamlit pywebview

# 3. Configure API Key
cp mykey_template.py mykey.py
# Edit mykey.py and fill in your LLM API Key

# 4. Launch
python webapp.py
```

> For more details on configuration and usage, please refer to the [original project](https://github.com/lsdefine/GenericAgent).

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---



## 🌟 项目简介

**GenericAgent_MM** 是在 [GenericAgent](https://github.com/lsdefine/GenericAgent) 基础上的二次开发，新增了**多模态记忆**能力。在 GenericAgent 极简自进化 Agent 框架（~3,300 行核心代码，7 个原子工具 + 92 行 Agent Loop 实现系统级控制）之上，GenericAgent_MM 引入了持久化多模态记忆系统 —— Agent 能够通过语义向量检索**记忆和召回文本与图片**，在交互中逐步构建对用户的个性化理解（偏好、照片、个人信息等）。交互越多，它越了解你。

> 🔗 原项目地址：[https://github.com/lsdefine/GenericAgent](https://github.com/lsdefine/GenericAgent)

---

## 🚀 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/small-code-cat/GenericAgent_MM.git
cd GenericAgent_MM

# 2. 安装依赖
pip install streamlit pywebview beautifulsoup4

# 3. 配置 API Key
cp mykey_template.py mykey.py
# 编辑 mykey.py，填入你的 LLM API Key

# 4. 启动
python webapp.py
```

> 更多配置和使用细节，请参考[原项目文档](https://github.com/lsdefine/GenericAgent)。

---

## 📄 许可

MIT License — 见 [LICENSE](LICENSE)