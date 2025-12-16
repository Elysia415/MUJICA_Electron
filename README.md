# MUJICA Electron

**MUJICA (Multi-stage User‑Judged Integration & Corroboration Architecture)** 的现代化 Electron 桌面应用重构版本。

本项目结合了 **Electron** 前端与 **FastAPI** 后端，提供了一个本地优先的学术论文研读与报告生成助手，支持从 OpenReview 抓取论文、构建本地向量知识库、以及多阶段的智能体写作与核查。

## 🏗 技术架构 (Architecture)

本项目采用前后端分离但本地集成的架构：

*   **前端 (Frontend)**
    *   **Electron**: 提供跨平台桌面应用壳。
    *   **React (Vite)**: 构建高性能、组件化的用户界面。
    *   **TailwindCSS**: 现代化的实用优先 CSS 框架，配合 Framer Motion 实现流畅动画。
    *   位于 `electron-app/` 目录。

*   **后端 (Backend)**
    *   **FastAPI**: 高性能 Python Web 框架，作为子进程由 Electron 启动。
    *   **Core Logic**: 复用原 `source/` 目录下的核心 Python 业务逻辑（爬虫、RAG、Agent Workflow）。
    *   位于 `backend/` 目录，通过 HTTP API 与前端通信。

*   **数据存储 (Data Persistence)**
    *   **SQLite**: 存储论文元数据、任务状态。
    *   **LanceDB**: 本地向量数据库，用于语义检索。
    *   所有数据默认存储在 `data/` 目录，完全本地化，隐私安全。

## ✨ 功能特性 (Key Features)

*   **本地知识库管理**: 支持批量导入、多维度筛选（年份/会议/决策）、批量删除与统计概览。
*   **深度调研报告**:
    *   **智能规划**: 自动拆解调研任务为多个子课题，检索 20+ 篇核心论文。
    *   **长文写作**: 生成 2000+ 字的深度综述，包含连贯的叙事与深度洞察。
    *   **导出功能**: 支持一键导出 Markdown 格式报告。
*   **严谨的事实核查**:
    *   **逐句验证**: 内置 Verifier Agent 对报告中的每一个论点进行 NLI (自然语言推理) 核查，覆盖 100+ 条目。
    *   **角标溯源**: 正文采用 `⁽ᴿˣ⁾` 角标引用，并提供详细的幻觉/冲突警告。
*   **历史记录自动保存**: 所有调研任务完成后自动归档，支持随时回溯查看。

## 🚀 快速开始 (Quick Start)

### 预置条件
- **Node.js**: (推荐 v18+)
- **Python**: (推荐 3.10+)

### 一键运行
在 Windows 环境下，直接双击运行根目录下的启动脚本：

```bash
run_mujica.bat
```

该脚本会自动：
1.  安装/检查 Python 后端依赖 (`backend/requirements.txt`)。
2.  安装/检查 Node.js 前端依赖 (`electron-app/` 和 `renderer/`)。
3.  启动后端 API 服务和 Electron 窗口。

## 🛠 开发指南 (Development)

如果您需要修改代码，建议分别启动前后端以获得热重载体验。

### 1. 启动后端 (Python)
```bash
# 在根目录下
pip install -r backend/requirements.txt
python backend/app.py
# API 服务默认运行在 http://127.0.0.1:8000
```

### 2. 启动前端 (Electron + React)
```bash
# 进入 electron-app 目录
cd electron-app

# 安装依赖（首次运行）
npm install
cd renderer && npm install && cd ..

# 启动开发模式（同时启动 React 开发服务器和 Electron）
npm run dev
```

## 📂 目录结构

```
MUJICA_Electron/
├── backend/            # FastAPI 后端入口与 API 定义
├── electron-app/       # Electron 主进程代码
│   ├── main/          # Electron 主进程逻辑
│   ├── renderer/      # React 前端代码 (Vite)
│   └── package.json
├── source/             # 核心业务逻辑 (复用原 Python 项目)
├── data/               # (自动生成) 数据库与下载的 PDF
├── run_mujica.bat      # Windows 一键启动脚本
└── README.md           # 本文件
```

## ⚠️ 注意事项
- **环境变量**: 请确保在根目录创建 `.env` 文件配置 API Key（如 OpenAI Key, OpenReview 账号等）。参考 `source/.env.example`。
- **端口占用**: 后端默认使用 `8000` 端口，React 开发服务器默认使用 `5173` 端口。

## License
MIT
