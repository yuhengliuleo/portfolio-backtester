# 📊 Portfolio Backtester / 投资组合回测器

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English

An interactive portfolio backtesting web application built with **Streamlit**. Supports multi-market, multi-asset portfolio analysis with advanced risk metrics, stress testing, and hedge analysis.

### Features

- **160+ Assets**: Full coverage of A-shares, Hong Kong, US stocks, Japan, Europe — ETFs, indices, and individual stocks
- **Unified Asset Selector**: Searchable dropdown with labels formatted as `Market · Type | Name (Ticker)`
- **Portfolio Backtesting**: Weighted return calculation with monthly/quarterly rebalancing
- **Performance Metrics**: Annualized return, Sharpe, Sortino, Max Drawdown, Calmar, Win Rate, Profit/Loss ratio
- **Interactive Charts**: Equity curve, drawdown analysis, annual returns, monthly heatmap (Plotly)
- **Stress Testing**: Pre-defined historical events (COVID crash, 2022 bear market, financial crises) with return/drawdown comparison
- **Hedge Analysis**: Optionally add a hedge asset and compare hedged vs. unhedged portfolio performance
- **Report Export**: One-click download of a complete HTML report with all charts and metrics

### Data Source

- **AKShare** (free, no API key required)
- **yfinance** (fallback for international indices — Europe, Japan, etc.)
- Automatic data caching in the `data/` folder

### Supported Markets

| Market | Coverage |
|--------|----------|
| 🇨🇳 A-Shares | CSI 300, SSE 50, CSI 500 indices; 60+ ETFs (broad, sector, commodity, bond, cross-border, QDII, currency, leveraged); 60+ individual stocks |
| 🇭🇰 Hong Kong | Tencent, Alibaba, Meituan, Xiaomi, BYD, JD, etc. |
| 🇺🇸 US Stocks | S&P 500 (SPY), Nasdaq 100 (QQQ), Dow Jones; AAPL, MSFT, NVDA, TSLA, etc.; GLD, SLV, TLT, etc. |
| 🇯🇵 Japan | Nikkei 225, TOPIX; domestic Japan ETFs |
| 🇪🇺 Europe | DAX, FTSE 100, CAC 40, Euro Stoxx 50; domestic Europe ETFs |

### Installation & Running

```bash
cd backtest_app

# Install dependencies
pip install -r requirements.txt

# Launch the app
streamlit run app.py
```

The browser will automatically open at http://localhost:8501

### Usage

1. **Configure Assets**: Use the searchable dropdown to select assets, set weights (%) for each
2. **Adjust Settings** (⚙️ tab): Start date, rebalancing frequency, benchmark index, stress test events, hedge asset
3. **Run Backtest**: Click 🚀 Run Backtest
4. **Analyze Results**: View equity curves, drawdowns, annual/monthly returns, stress test comparisons
5. **Export**: Download the full HTML report

### Project Structure

```
backtest_app/
├── app.py           # Streamlit main application
├── utils.py         # Data download, calculation, and chart utilities
├── requirements.txt # Python dependencies
├── data/            # Data cache directory (auto-created)
└── README.md
```

---

<a name="中文"></a>
## 中文

基于 Streamlit 的交互式投资组合回测应用，支持多市场、多资产回测分析。

### 功能

- **160+ 资产**：覆盖 A股/港股/美股/日本/欧洲，含 ETF、指数、个股
- **统一资产选择器**：搜索式下拉框，格式 `市场 · 类型 | 名称 (代码)`
- **组合回测**：加权收益计算，支持月度/季度再平衡
- **绩效指标**：年化回报、Sharpe、Sortino、Max Drawdown、Calmar、胜率、盈亏比
- **交互式图表**：权益曲线、回撤分析、年度收益对比、月度热力图（Plotly）
- **压力测试**：预定义历史事件（COVID、熊市、金融危机等）回报/回撤对比
- **对冲分析**：可选添加对冲资产，对比含对冲组合表现
- **报告导出**：一键下载完整 HTML 报告

### 数据源

- **AKShare**（免费，无需 API Key）
- **yfinance**（回退方案，支持欧洲/日本等国际指数）
- 数据自动缓存到 `data/` 文件夹

### 支持的市场

| 市场 | 覆盖范围 |
|------|---------|
| 🇨🇳 A股 | 沪深300、上证50、中证500 等指数；60+ ETF（宽基/行业/商品/债券/跨境/QDII/货币/杠杆）；60+ 个股 |
| 🇭🇰 港股 | 腾讯、阿里、美团、小米、比亚迪、京东等 |
| 🇺🇸 美股 | 标普500(SPY)、纳指100(QQQ)、道指；AAPL、MSFT、NVDA、TSLA 等个股；GLD、TLT 等 ETF |
| 🇯🇵 日本 | 日经225、东证指数；日经ETF(国内) |
| 🇪🇺 欧洲 | 德国DAX、英国富时100、法国CAC40、欧洲斯托克50；德国ETF(国内) |

### 安装与运行

```bash
cd backtest_app

# 安装依赖
pip install -r requirements.txt

# 启动应用
streamlit run app.py
```

浏览器会自动打开 http://localhost:8501

### 使用方法

1. **配置资产**：使用搜索式下拉框选择资产，设置权重(%)
2. **调整参数**（⚙️ 设置标签页）：起始日期、再平衡频率、基准指数、压力测试事件、对冲资产
3. **运行回测**：点击 🚀 运行回测
4. **分析结果**：查看权益曲线、回撤、年度/月度收益、压力测试对比
5. **导出报告**：下载 HTML 完整报告

### 文件结构

```
backtest_app/
├── app.py           # Streamlit 主应用
├── utils.py         # 数据下载、计算、图表工具函数
├── requirements.txt # Python 依赖
├── data/            # 数据缓存目录（自动创建）
└── README.md
```

---

## License

MIT License — For educational and research purposes only. Not financial advice.