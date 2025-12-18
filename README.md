<p align="center">
  <img src="electron-app/assets/icon.png" alt="MUJICA Logo" width="128" />
</p>

<h1 align="center">MUJICA Desktop</h1>

<p align="center">
  <strong>Multi-stage User-Judged Integration & Corroboration Architecture</strong><br/>
  基于循证写作专家的学术论文深度分析与综述生成工具
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows-blue?logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Electron-26.6-47848F?logo=electron" alt="Electron" />
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react" alt="React" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
</p>

---

## 📖 项目简介

**MUJICA** 是一款本地优先、保护隐私的 AI 研究助手，专为需要深度阅读和撰写学术综述的研究者设计。它能够：

- 📚 **构建本地知识库**：从 OpenReview 等平台导入会议论文，自动解析 PDF 并建立向量索引
- 🔍 **智能语义检索**：基于 LanceDB 的本地向量数据库，支持自然语言查询
- ✍️ **自动化深度写作**：根据研究问题，自动规划调研路径，生成 2000+ 字的学术综述
- ✅ **严格事实核查**：内置验证代理，对每一个论点进行 NLI 推理核查，识别潜在幻觉

---

## ✨ 核心功能

### 1. 📂 智能知识库管理

| 功能           | 说明                                                        |
| -------------- | ----------------------------------------------------------- |
| **数据导入**   | 支持从 OpenReview 批量抓取会议论文，自动下载 PDF 并解析全文 |
| **混合搜索**   | 🔤 关键词搜索 + 🧠 语义搜索（向量检索），一键切换             |
| **元数据浏览** | 查看论文评分、录用状态、作者信息、评审意见和 Rebuttal       |
| **批量管理**   | 支持多选删除、导入/导出知识库备份（ZIP 格式）               |

### 2. 📝 Agentic 研究工作流

MUJICA 采用多阶段 Agent 架构，模拟人类研究者的完整思维路径：

<p align="center">
  <img src="electron-app/assets/stucture.png" alt="MUJICA Workflow Structure" width="800" />
</p>

```
[用户查询] → [Planner Agent] → [Researcher Agent] → [Writer Agent] → [Verifier Agent]
```

- **Planner**：将复杂问题拆解为可执行的子课题
- **Researcher**：从知识库中检索 20+ 篇相关论文的证据片段
- **Writer**：基于证据撰写结构化的长文综述（避免幻觉）
- **Verifier**：对报告中的每一个论点进行逐句核查

### 3. ✅ 自动化事实核查

验证代理会对生成的报告进行三级验证：

| 状态            | 含义                               |
| --------------- | ---------------------------------- |
| 🟢 **Verified**  | 论点有确凿证据支持                 |
| 🟡 **Uncertain** | 证据支持度不足或存在歧义           |
| 🔴 **Conflict**  | 论点与源文件直接冲突（检测到幻觉） |

每个验证结果都附带原文引用和判定理由，确保透明可溯源。

### 4. 🔗 交互式报告体验

- **点击即达**：报告中的引用标签（如 `[R5]`）可点击，自动定位到右侧证据面板
- **深度溯源**：证据卡片支持一键跳转至知识库，查看完整论文详情
- **专业排版**：优化的 Markdown 渲染，支持数学公式、代码高亮和层级清晰的章节标题

### 5. 🔒 本地优先与隐私保护

- **数据全程本地化**：所有论文 PDF、向量索引和元数据均存储在本地 `data/` 目录
- **无云端依赖**：除 LLM API 调用外，不连接任何外部服务
- **灵活配置**：支持任意 OpenAI 兼容 API（OpenAI, Anthropic, DeepSeek 等）

---

## 🛠 技术架构

采用现代化的双进程架构，确保性能与扩展性：

```
┌─────────────────────────────────────────────────────────────┐
│                     MUJICA Desktop                          │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐     HTTP      ┌───────────────────┐  │
│  │   Electron Shell  │ ←──────────→ │   Python Backend   │  │
│  │   + React UI      │   :8000       │   (FastAPI)        │  │
│  │                   │               │                    │  │
│  │  • Vite           │               │  • LLM Agents      │  │
│  │  • TailwindCSS    │               │  • LanceDB         │  │
│  │  • Framer Motion  │               │  • SQLite          │  │
│  └───────────────────┘               └───────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

| 组件     | 技术栈                                | 说明              |
| -------- | ------------------------------------- | ----------------- |
| **前端** | Electron + React + Vite + TailwindCSS | 高性能桌面 UI     |
| **后端** | Python + FastAPI + LanceDB + SQLite   | AI 推理与数据处理 |
| **打包** | PyInstaller + Electron Builder        | 生成免安装/安装包 |

---

## 🚀 安装与使用

### 方式一：下载安装包（推荐）

1. 前往 [Releases](https://github.com/Elysia415/MUJICA_Electron/releases) 页面
2. 下载最新的 `MUJICA Setup x.x.x.exe`
3. 运行安装程序，按提示完成安装
4. 启动应用，在设置中配置 API Key



### 初始配置

首次运行后，点击左下角 **Settings (⚙️)** 配置：

| 配置项              | 说明                                | 必填 |
| ------------------- | ----------------------------------- | ---- |
| **OpenAI API Key**  | 用于驱动 LLM Agent                  | ✅    |
| **OpenAI Base URL** | 自定义 API 端点（兼容 DeepSeek 等） | 可选 |
| **Embedding Model** | 向量模型（用于语义搜索）            | 可选 |
| **OpenReview 账号** | 用于抓取论文（可不填）              | 可选 |

---

## ⌨️ 开发指南

### 环境要求

- **Node.js**: 18+
- **Python**: 3.10+
- **Git**

### 从源码运行

```bash
# 1. 克隆项目
git clone https://github.com/Elysia415/MUJICA_Electron.git
cd MUJICA_Electron

# 2. 安装后端依赖
pip install -r backend/requirements.txt

# 3. 安装前端依赖
cd electron-app
npm install
cd renderer && npm install && cd ..

# 4. 启动开发模式
npm run dev
```

### 打包发布

```bash
# 1. 打包 Python 后端
pyinstaller backend/mujica_backend.spec --clean --noconfirm --distpath backend/dist --workpath backend/build

# 2. 打包 Electron 应用
cd electron-app
npm run dist
```

输出位置：`electron-app/release/`

---

## 📁 项目结构

```
MUJICA_Electron/
├── backend/                 # Python 后端
│   ├── app.py              # FastAPI 入口
│   ├── job_manager.py      # 任务调度器
│   └── mujica_backend.spec # PyInstaller 配置
├── electron-app/            # Electron 前端
│   ├── main/               # 主进程
│   ├── renderer/           # React 渲染进程
│   ├── assets/             # 图标资源
│   └── package.json        # 构建配置
├── source/                  # 核心业务逻辑
│   └── src/
│       ├── data_engine/    # 数据抓取与存储
│       ├── planner/        # 规划 Agent
│       ├── researcher/     # 研究 Agent
│       ├── writer/         # 写作 Agent
│       └── verifier/       # 验证 Agent
├── data/                    # (运行时生成) 数据库与 PDF
├── run_mujica.bat           # Windows 一键启动脚本
└── README.md
```

---

## 🙏 致谢

- [LanceDB](https://lancedb.com/) - 高性能本地向量数据库
- [OpenReview](https://openreview.net/) - 学术论文数据来源
- [Electron](https://www.electronjs.org/) - 跨平台桌面应用框架

---

## 📄 License

MIT License © 2025 Elysia415
