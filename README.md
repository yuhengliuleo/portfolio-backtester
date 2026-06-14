# 📊 LLM 投资组合回测工具

**通过自然语言对话配置投资组合，一键生成专业回测报告**

An AI-powered portfolio backtesting tool that lets you configure investment portfolios through natural language conversation.

---

## 🇨🇳 中文

### 简介

这是一个基于 **Streamlit** + **AKShare** + **OpenAI API** 的投资组合回测 Web 应用。你可以：

- 🤖 **用自然语言描述投资组合**（如"60% 沪深300 + 20% 黄金 + 20% 国债"），AI 自动解析为配置
- 📊 **一键运行回测**，查看权益曲线、回撤、年度/月度收益热力图
- ⚡ **压力测试**，分析在 COVID、熊市、金融危机等极端事件下的表现
- 🛡️ **对冲分析**，对比添加对冲资产（如黄金）前后的组合表现
- 📥 **下载完整 HTML 报告**，包含所有图表和指标

### 功能特性

| 功能 | 说明 |
|------|------|
| AI 对话配置 | 支持任意 OpenAI 兼容 API（DeepSeek、通义千问等） |
| 全球市场覆盖 | A股、港股、美股、ETF（通过 AKShare 免费数据源） |
| 交互式图表 | 基于 Plotly，支持缩放、悬停、导出 |
| 压力测试 | 预设 6 大历史事件，支持自定义时间范围 |
| 对冲分析 | 自动计算添加对冲资产后的风险收益变化 |
| 缓存机制 | 本地缓存数据，避免重复下载 |

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/yuhengliuleo/llm-portfolio-backtester.git
cd llm-portfolio-backtester

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行应用
streamlit run app.py
```

运行后浏览器会自动打开 `http://localhost:8501`。

### 使用指南

1. **配置 AI**（可选）：前往 ⚙️ 设置 → AI 配置，输入 OpenAI 兼容 API 的 Base URL、API Key 和 Model
2. **AI 对话**：在 🤖 AI 对话 标签页输入自然语言描述，如"帮我配一个稳健型组合：沪深300 40%、中证500 20%、国债ETF 20%、黄金ETF 20%"
3. **手动配置**：前往 📊 回测 标签页，手动输入 Ticker 和权重
4. **查看结果**：点击"🚀 运行回测"，在多个标签页查看权益曲线、回撤、压力测试等
5. **下载报告**：在"📥 下载报告"标签页下载完整 HTML 报告

### 支持的资产代码

| 市场 | 示例代码 |
|------|---------|
| A股指数 | `sh000300`（沪深300）、`sh000905`（中证500）、`sh000016`（上证50） |
| A股 ETF | `sh510300`（沪深300ETF）、`sh518880`（黄金ETF）、`sh511010`（国债ETF） |
| 美股 | `SPY`（标普500）、`QQQ`（纳指100）、`GLD`（黄金）、`TLT`（长债） |
| 港股 | `00700`（腾讯）、`09988`（阿里）、`03690`（美团） |

---

## 🇬🇸 English

### Introduction

A **Streamlit** + **AKShare** + **OpenAI API** web application for portfolio backtesting. Features:

- 🤖 **Natural language portfolio configuration** — describe your allocation in plain language, AI parses it automatically
- 📊 **One-click backtesting** — equity curve, drawdown, annual/monthly returns heatmap
- ⚡ **Stress testing** — analyze performance during COVID, bear markets, financial crises
- 🛡️ **Hedge analysis** — compare portfolios with and without hedging assets (e.g., gold)
- 📥 **Downloadable HTML reports** — complete with all charts and metrics

### Features

| Feature | Description |
|---------|-------------|
| AI Chat Config | Works with any OpenAI-compatible API (DeepSeek, Qwen, etc.) |
| Global Markets | A-shares, HK stocks, US stocks, ETFs (via AKShare, free data) |
| Interactive Charts | Built with Plotly — zoom, hover, export |
| Stress Testing | 6 preset historical events + custom date ranges |
| Hedge Analysis | Automatically compute risk/return with hedge overlay |
| Caching | Local data cache to avoid redundant downloads |

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/yuhengliuleo/llm-portfolio-backtester.git
cd llm-portfolio-backtester

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

The browser will open automatically at `http://localhost:8501`.

### Quick Start

1. **Configure AI** (optional): Go to ⚙️ Settings → AI Config, enter your OpenAI-compatible API credentials
2. **AI Chat**: In the 🤖 AI Chat tab, describe your portfolio in natural language
3. **Manual Config**: Go to 📊 Backtest tab, enter tickers and weights manually
4. **View Results**: Click "🚀 Run Backtest", explore equity curve, drawdown, stress tests across tabs
5. **Download Report**: Download the full HTML report from the "📥 Download" tab

### Supported Ticker Examples

| Market | Examples |
|--------|----------|
| A-share Indices | `sh000300` (CSI 300), `sh000905` (CSI 500), `sh000016` (SSE 50) |
| A-share ETFs | `sh510300` (CSI 300 ETF), `sh518880` (Gold ETF), `sh511010` (Bond ETF) |
| US Stocks | `SPY` (S&P 500), `QQQ` (Nasdaq 100), `GLD` (Gold), `TLT` (Long Bond) |
| HK Stocks | `00700` (Tencent), `09988` (Alibaba), `03690` (Meituan) |

---

## 📁 项目结构 / Project Structure

```
backtest_app/
├── app.py              # 主应用（Streamlit UI）/ Main application
├── utils.py            # 工具函数（数据、图表、报告）/ Utilities
├── requirements.txt    # Python 依赖 / Dependencies
├── .gitignore          # Git 忽略文件
├── data/               # 数据缓存目录（自动创建）/ Data cache (auto-created)
└── README.md           # 本文件 / This file
```

## 📄 许可证 / License

MIT License

## ⚠️ 免责声明 / Disclaimer

本工具仅供学习和研究使用，不构成任何投资建议。投资有风险，入市需谨慎。

This tool is for educational and research purposes only. It does not constitute investment advice. Investing involves risk.