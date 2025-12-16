
<div align="center">

<!-- <img src="assets/preview.png" width="200" height="auto" alt="Logo Placehoder - 请替换为你的Logo或保留此默认图"> -->

# 🐱 OtakuNeko | 御宅猫

*你的二次元赛博嘴替 —— 基于 LLM 的智能化私人番剧管理与分析助手*

**中文 | [English](README_EN.md)**

<p>
    <a href="https://www.python.org/">
        <img src="https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
    </a>
    <a href="https://streamlit.io/">
        <img src="https://img.shields.io/badge/Streamlit-App-ff4b4b?style=flat-square&logo=streamlit&logoColor=white" alt="Streamlit">
    </a>
    <a href="#">
        <img src="https://img.shields.io/badge/AI-DeepSeek-blueviolet?style=flat-square" alt="DeepSeek">
    </a>
    <a href="LICENSE">
        <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
    </a>
</p>

<p>
    <b>OtakuNeko 不仅仅是一个记录工具。</b><br>
    它能同步你的 Bangumi 收藏，利用 AI 深度分析你的看番口味，<br>
    生成精美的年度总结海报，并提供真正懂你的番剧推荐。
</p>

<br>

*如果该项目对你有用, 欢迎 star 🌟 & fork 🍴*

<br>

</div>

## ✨ 核心功能

OtakuNeko 旨在解决传统番剧管理工具“只记录不分析”的痛点，通过 LLM 为你的二次元生活赋能。

### 1. 🧠 AI 深度画像
告别枯燥的统计图表，让 AI 告诉你真正的自己。
- **成分鉴定**：生成“纯爱战神”、“乐子人”、“赛博案底”等趣味标签。
- **多重人格**：支持切换 **“毒舌猫娘”** 或 **“专业评论家”** 语调，让分析报告充满“人味”。

### 2. 🏆 年度动画报告
一键生成 4x3 布局的精美年度总结海报，包含 12 个深度维度：
- **深度评选**：年度声优、最忙月份、最佳动画、最意难平...
- **自动绘图**：无需设计，自动抓取封面图并排版，支持一键下载分享。

### 3. 📊 数据同步 & 智能推荐
- **无感同步**：一键拉取 Bangumi (bgm.tv) 收藏，自动整理“看过/在看/想看”。
- **向量推荐**：基于向量数据库 (Vector Store)，告别大众榜单，推荐符合你口味的冷门佳作。

---

## 📸 界面预览

<div align="center">
    <img src="assets/preview.png" width="800" alt="Dashboard Preview">
    <br>
    <i>OtakuNeko 控制台界面预览</i>
</div>

---

## 🛠️ 快速开始

无需掌握复杂的命令行，我们为 Windows 用户提供了极致的懒人启动方案。

### 1. 环境初始化
在项目根目录下，双击运行脚本：
```bash
Setup.bat
```

> ⏳ **说明**：脚本会自动创建 Python 虚拟环境并安装所有依赖，仅需初次运行一次。

### 2. 启动程序双击运行脚本：

```bash
Run.vbs

```

### 3. 配置 API Key
在弹出的框里，填入你的 DeepSeek API Key（目前仅支持OpenAI接口的模型），Bungumi token，Bungumi的用户名。

```ini
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> 🎉 **成功**：程序将在后台静默运行，并自动在浏览器打开 `http://localhost:8501`。

---

## 📂 目录结构
```text
OtakuNeko/
├── data/                  # 📦 数据存储 (JSON数据集、生成的年度海报)
├── src/                   # 🧠 核心源码
│   ├── agent/             # AI 智能体 (Profile, Recommend, YearReport)
│   ├── plugins/           # 插件系统
│   └── services/          # 基础服务 (BgmServe, LLMService)
├── venv/                  # 🐍 虚拟环境 (自动生成)
├── app.py                 # 🚀 Streamlit 主入口
├── .env                   # 🔑 配置文件
├── 一键配置.bat           # 🛠️ 环境初始化脚本
├── 启动程序.bat           # 💻 调试启动脚本 (带黑窗口)
└── 无窗口启动.vbs         # ✨ 静默启动脚本 (推荐)

```

## 📖 使用指南| 模块 | 操作说明 |
| --- | --- |
| **控制台 (Sidebar)** | • **🔄 一键全量更新**：初次使用或看完新番后同步数据<br>

<br>• **🧩 扩展插件**：点击生成“2025 年度动画报告”<br>

<br>• **🎭 助手风格**：随时切换 AI 说话风格 |
| **对话框 (Chat)** | 直接输入自然语言指令，例如：<br>

<br>• “分析一下我最近的看番口味”<br>

<br>• “推荐几部剧情像《命运石之门》一样的番” |
| **关闭程序** | 使用完毕后，**务必**点击侧边栏底部的 **“❌ 关闭程序”** 按钮以释放后台资源。 |

## 📝 FAQ
<details>
<summary><strong>Q: 启动时命令行提示中文乱码？</strong></summary>
A: 这是一个 Windows 已知问题。请直接使用 <code>无窗口启动.vbs</code> 启动，或者直接双击 <code>启动程序.bat</code>（脚本内已内置 UTF-8 修复），不要在 PowerShell 中手动运行。
</details>

<details>
<summary><strong>Q: 年度报告生成失败或图片加载不出？</strong></summary>
A: 生成海报需要访问 Bangumi 的图片服务器，请确保你的网络环境可以正常访问 bgm.tv 的图片资源。
</details>

<details>
<summary><strong>Q: 如何更新项目依赖？</strong></summary>
A: 如果项目有更新，再次运行 <code>一键配置.bat</code> 即可自动更新 requirements.txt 中的依赖。
</details>

## 📜 License
本项目采用 [MIT License](https://www.google.com/search?q=LICENSE) 协议进行开源。

