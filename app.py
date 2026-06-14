"""
Streamlit 投资组合回测器
========================
本地运行：streamlit run app.py
"""

import os
import sys
import datetime as dt
import time

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 添加当前目录到路径（确保 utils 可被导入）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import (
    STRESS_EVENTS,
    download_data,
    calculate_portfolio_returns,
    calculate_benchmark_portfolio_returns,
    calculate_benchmark_returns,
    compute_metrics,
    plot_equity_curve,
    plot_drawdown,
    plot_monthly_heatmap,
    plot_annual_returns,
    stress_test,
    plot_stress_test,
    calculate_hedge_portfolio,
    generate_html_report,
    ASSET_CATALOG,
    search_assets,
    get_assets_by_market,
    detect_market,
)


# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="投资组合回测器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 自定义样式
# ============================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .setting-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
    }
    .weight-ok { color: #28a745; font-weight: bold; }
    .weight-warn { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Session State 初始化
# ============================================================
# 组合资产
if "asset_rows" not in st.session_state:
    st.session_state.asset_rows = [
        {"ticker": "sh000300", "weight": 40, "name": "沪深300", "select_mode": "📂 浏览"},
        {"ticker": "SPY", "weight": 30, "name": "标普500 ETF", "select_mode": "📂 浏览"},
        {"ticker": "GLD", "weight": 30, "name": "黄金ETF", "select_mode": "📂 浏览"},
    ]

# 基准资产（多资产）
if "benchmark_rows" not in st.session_state:
    st.session_state.benchmark_rows = [
        {"ticker": "sh000300", "weight": 60, "name": "沪深300", "select_mode": "📂 浏览"},
        {"ticker": "TLT", "weight": 40, "name": "长期国债ETF", "select_mode": "📂 浏览"},
    ]

if "backtest_results" not in st.session_state:
    st.session_state.backtest_results = None
if "start_date" not in st.session_state:
    st.session_state.start_date = dt.date(2018, 1, 1)
if "rebalance" not in st.session_state:
    st.session_state.rebalance = "每月"
if "selected_stress" not in st.session_state:
    st.session_state.selected_stress = ["2020-COVID", "2022-熊市"]
if "hedge_enabled" not in st.session_state:
    st.session_state.hedge_enabled = False
if "hedge_ticker" not in st.session_state:
    st.session_state.hedge_ticker = "sh518880"
if "hedge_weight" not in st.session_state:
    st.session_state.hedge_weight = 0.1


# ============================================================
# 侧边栏：快速参考
# ============================================================
with st.sidebar:
    st.markdown("### ℹ️ 快速参考")
    st.markdown("""
    **常见 Ticker 格式：**
    | 类型 | 示例 |
    |------|------|
    | A股指数 | `sh000300` (沪深300) |
    | A股ETF | `sh510300` |
    | A股个股 | `600519` (贵州茅台) |
    | 港股 | `00700` (腾讯) |
    | 美股 | `AAPL`, `SPY`, `TLT` |
    | 加密货币 | `BTC-USD` |
    | 欧洲指数 | `^GDAXI` (DAX) |
    """)

    st.markdown("---")
    st.markdown("### 📊 支持的市场")
    for market_name, types in ASSET_CATALOG.items():
        with st.expander(market_name):
            for type_name, assets in types.items():
                st.markdown(f"**{type_name}** ({len(assets)}个)")
                items = [f"{name} ({ticker})" for name, ticker in list(assets.items())[:5]]
                for item in items:
                    st.markdown(f"  - {item}")
                if len(assets) > 5:
                    st.markdown(f"  - ... 等 {len(assets)} 个")

    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #999; font-size: 12px;">
    ⚠️ 仅供学习研究，不构成投资建议<br>
    数据源: AKShare / yfinance
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 页面标题
# ============================================================
st.markdown('<div class="main-header">📊 投资组合回测器</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">配置组合资产和基准，一键回测，分析表现</div>', unsafe_allow_html=True)


# ============================================================
# 辅助函数：渲染资产选择行
# ============================================================
def render_asset_selector(key_prefix: str, row_data: dict, idx: int) -> dict:
    """
    渲染一行资产选择器（浏览模式或搜索模式），返回更新后的 row_data。
    """
    # 精简的一行布局
    cols = st.columns([1, 5, 2, 0.5])

    with cols[0]:
        # 模式切换
        mode = st.radio(
            "模式",
            ["📂 浏览", "🔍 搜索"],
            index=0 if row_data.get("select_mode", "📂 浏览") == "📂 浏览" else 1,
            key=f"{key_prefix}_mode_{idx}",
            horizontal=True,
            label_visibility="collapsed",
        )
        row_data["select_mode"] = mode

    with cols[1]:
        if mode == "📂 浏览":
            # 三级浏览选择
            c1, c2, c3 = st.columns(3)
            with c1:
                market = st.selectbox(
                    "市场",
                    list(ASSET_CATALOG.keys()),
                    key=f"{key_prefix}_market_{idx}",
                )
            with c2:
                types = get_assets_by_market(market)
                type_name = st.selectbox(
                    "类型",
                    list(types.keys()),
                    key=f"{key_prefix}_type_{idx}",
                )
            with c3:
                assets = types.get(type_name, {})
                asset_options = {f"{name} ({ticker})": ticker for name, ticker in assets.items()}
                # 找到当前 ticker 对应的选项
                current_label = None
                for label, t in asset_options.items():
                    if t == row_data.get("ticker"):
                        current_label = label
                        break
                if current_label is None and asset_options:
                    current_label = list(asset_options.keys())[0]

                selected_label = st.selectbox(
                    "标的",
                    list(asset_options.keys()),
                    index=list(asset_options.keys()).index(current_label) if current_label in asset_options else 0,
                    key=f"{key_prefix}_asset_{idx}",
                )
                ticker = asset_options.get(selected_label, "")
                name = selected_label.split(" (")[0] if " (" in selected_label else selected_label
                row_data["ticker"] = ticker
                row_data["name"] = name
        else:
            # 搜索模式
            keyword = st.text_input(
                "搜索关键词",
                value=row_data.get("name", ""),
                placeholder="输入资产名称/代码，如 茅台、AAPL、黄金",
                key=f"{key_prefix}_search_{idx}",
            )
            if keyword:
                results = search_assets(keyword)
                if results:
                    label_map = {r["label"]: r["ticker"] for r in results}
                    # 找到当前 ticker 对应的选项
                    current_label = None
                    for label, t in label_map.items():
                        if t == row_data.get("ticker"):
                            current_label = label
                            break
                    if current_label is None:
                        current_label = list(label_map.keys())[0]

                    selected_label = st.selectbox(
                        f"找到 {len(results)} 个结果",
                        list(label_map.keys()),
                        index=list(label_map.keys()).index(current_label) if current_label in label_map else 0,
                        key=f"{key_prefix}_result_{idx}",
                    )
                    ticker = label_map.get(selected_label, "")
                    name = selected_label.split(" | ")[-1].split(" (")[0] if " | " in selected_label else selected_label
                    row_data["ticker"] = ticker
                    row_data["name"] = name
                else:
                    # 允许手动输入
                    manual_ticker = st.text_input(
                        "手动输入 Ticker",
                        value=row_data.get("ticker", ""),
                        placeholder="如 AAPL, sh000300, 00700",
                        key=f"{key_prefix}_manual_{idx}",
                    )
                    if manual_ticker:
                        row_data["ticker"] = manual_ticker.strip()
                        row_data["name"] = manual_ticker.strip()

    with cols[2]:
        # 权重输入
        weight = st.number_input(
            "权重(%)",
            min_value=0.0,
            max_value=100.0,
            value=float(row_data.get("weight", 0)),
            step=5.0,
            key=f"{key_prefix}_weight_{idx}",
        )
        row_data["weight"] = weight

    return row_data


# ============================================================
# Tab 1: 🏠 回测主页
# ============================================================
# 使用 tabs 替代 sidebar
tab_main, tab_settings = st.tabs(["🏠 回测", "⚙️ 设置"])

with tab_main:
    # --- 📁 我的组合 ---
    st.subheader("📁 我的组合（投资组合）")
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)

    # 渲染每个资产行
    for i, row in enumerate(st.session_state.asset_rows):
        st.session_state.asset_rows[i] = render_asset_selector("port", row, i)

    # 添加/删除按钮 + 权重总和
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 3])
    with btn_col1:
        if st.button("➕ 添加资产", key="add_portfolio"):
            st.session_state.asset_rows.append(
                {"ticker": "", "weight": 10, "name": "", "select_mode": "📂 浏览"}
            )
            st.rerun()
    with btn_col2:
        if len(st.session_state.asset_rows) > 1:
            if st.button("➖ 删除最后一行", key="del_portfolio"):
                st.session_state.asset_rows.pop()
                st.rerun()

    # 权重总和显示
    total_weight = sum(r["weight"] for r in st.session_state.asset_rows)
    if abs(total_weight - 100) < 1:
        st.markdown(f'<p class="weight-ok">✅ 权重总和: {total_weight:.0f}%</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="weight-warn">⚠️ 权重总和: {total_weight:.0f}%（将自动归一化）</p>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # --- 📊 参考基准 ---
    st.subheader("📊 参考基准（基准组合）")
    st.markdown("支持多资产加权基准。默认为 60% 沪深300 + 40% 长期国债。")
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)

    # 渲染每个基准资产行
    for i, row in enumerate(st.session_state.benchmark_rows):
        st.session_state.benchmark_rows[i] = render_asset_selector("bench", row, i)

    # 添加/删除按钮 + 权重总和
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 3])
    with btn_col1:
        if st.button("➕ 添加基准资产", key="add_benchmark"):
            st.session_state.benchmark_rows.append(
                {"ticker": "", "weight": 10, "name": "", "select_mode": "📂 浏览"}
            )
            st.rerun()
    with btn_col2:
        if len(st.session_state.benchmark_rows) > 1:
            if st.button("➖ 删除最后一行", key="del_benchmark"):
                st.session_state.benchmark_rows.pop()
                st.rerun()

    # 基准权重总和
    bench_total = sum(r["weight"] for r in st.session_state.benchmark_rows)
    if abs(bench_total - 100) < 1:
        st.markdown(f'<p class="weight-ok">✅ 基准权重总和: {bench_total:.0f}%</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="weight-warn">⚠️ 基准权重总和: {bench_total:.0f}%（将自动归一化）</p>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # --- 🚀 运行回测 ---
    st.markdown("")
    run_col1, run_col2, run_col3 = st.columns([1, 2, 1])
    with run_col2:
        run_clicked = st.button(
            "🚀 运行回测", type="primary", width="stretch", use_container_width=True
        )

    # --- 执行回测逻辑 ---
    if run_clicked:
        # 验证组合
        asset_rows = st.session_state.asset_rows
        tickers = [r["ticker"] for r in asset_rows if r.get("ticker")]
        weights = [r["weight"] / 100.0 for r in asset_rows if r.get("ticker")]

        if len(tickers) == 0:
            st.error("❌ 请至少添加一个资产")
            st.stop()

        weight_sum = sum(weights)
        if abs(weight_sum - 1.0) > 0.05:
            st.warning(f"⚠️ 权重总和为 {weight_sum:.3f}，将自动归一化。")
            weights = [w / weight_sum for w in weights]

        # 验证基准
        bench_rows = st.session_state.benchmark_rows
        bench_tickers = [r["ticker"] for r in bench_rows if r.get("ticker")]
        bench_weights = [r["weight"] / 100.0 for r in bench_rows if r.get("ticker")]

        if len(bench_tickers) == 0:
            st.error("❌ 请至少添加一个基准资产")
            st.stop()

        bench_ws = sum(bench_weights)
        if abs(bench_ws - 1.0) > 0.05:
            bench_weights = [w / bench_ws for w in bench_weights]

        tickers_str = ", ".join(tickers)
        weights_str = ", ".join(f"{w:.2f}" for w in weights)
        bench_str = ", ".join(bench_tickers)
        bench_w_str = ", ".join(f"{w:.2f}" for w in bench_weights)

        start_date = st.session_state.start_date
        rebalance = st.session_state.rebalance
        end_date_str = dt.date.today().strftime("%Y-%m-%d")
        start_date_str = (
            start_date.strftime("%Y-%m-%d")
            if isinstance(start_date, dt.date)
            else str(start_date)
        )

        # 进度条
        progress = st.progress(0, text="📥 正在下载组合数据...")

        # 下载组合数据
        prices, invalid_tickers = download_data(tickers, start_date_str, end_date_str)

        if invalid_tickers:
            st.warning(f"⚠️ 以下 Ticker 下载失败: {', '.join(invalid_tickers)}")
            valid_pairs = [
                (t, w) for t, w in zip(tickers, weights) if t not in invalid_tickers
            ]
            if valid_pairs:
                tickers, weights = zip(*valid_pairs)
                tickers, weights = list(tickers), list(weights)
                ws = sum(weights)
                weights = [w / ws for w in weights]
                prices = prices[tickers]
            else:
                st.error("❌ 所有 Ticker 均下载失败，无法执行回测")
                st.stop()

        progress.progress(25, text="📥 正在下载基准数据...")

        # 下载基准数据
        bench_prices, bench_invalid = download_data(bench_tickers, start_date_str, end_date_str)
        has_benchmark = len(bench_invalid) == 0 and not bench_prices.empty
        if not has_benchmark:
            # 部分基准资产失败
            valid_bench = [(t, w) for t, w in zip(bench_tickers, bench_weights) if t not in bench_invalid]
            if valid_bench:
                bench_tickers, bench_weights = zip(*valid_bench)
                bench_tickers, bench_weights = list(bench_tickers), list(bench_weights)
                bw = sum(bench_weights)
                bench_weights = [w / bw for w in bench_weights]
                bench_prices = bench_prices[bench_tickers]
                has_benchmark = True
            else:
                st.warning("⚠️ 所有基准资产下载失败，将不显示基准对比")

        progress.progress(45, text="📊 正在计算组合收益...")

        # 计算组合收益
        portfolio_returns = calculate_portfolio_returns(prices, weights, rebalance)
        portfolio_cum = (1 + portfolio_returns).cumprod()

        # 计算基准收益（支持多资产加权）
        benchmark_returns = None
        benchmark_cum = None
        if has_benchmark:
            if len(bench_tickers) == 1:
                benchmark_returns = calculate_benchmark_returns(bench_prices.iloc[:, 0])
            else:
                benchmark_returns = calculate_benchmark_portfolio_returns(bench_prices, bench_weights)
            benchmark_cum = (1 + benchmark_returns).cumprod()
            common_idx = portfolio_cum.index.intersection(benchmark_cum.index)
            portfolio_cum = portfolio_cum.loc[common_idx]
            benchmark_cum = benchmark_cum.loc[common_idx]
            portfolio_returns = portfolio_returns.loc[common_idx]
            benchmark_returns = benchmark_returns.loc[common_idx]

        progress.progress(60, text="📊 正在计算绩效指标...")

        # 计算指标
        port_metrics = compute_metrics(portfolio_returns, "组合")
        metrics_list = [port_metrics]
        if has_benchmark and benchmark_returns is not None:
            bench_metrics = compute_metrics(benchmark_returns, "基准")
            metrics_list.append(bench_metrics)
        metrics_df = pd.DataFrame(metrics_list)

        progress.progress(70, text="📉 正在计算回撤...")

        # 对冲计算
        hedge_cum = None
        hedge_enabled = st.session_state.hedge_enabled
        hedge_ticker = st.session_state.hedge_ticker
        hedge_weight = st.session_state.hedge_weight

        if hedge_enabled and hedge_ticker:
            with st.spinner("正在计算对冲组合..."):
                _, hedge_returns = calculate_hedge_portfolio(
                    prices, weights, hedge_ticker, hedge_weight, rebalance
                )
                if hedge_returns is not None:
                    hedge_cum = (1 + hedge_returns).cumprod()
                    common_idx = portfolio_cum.index.intersection(hedge_cum.index)
                    hedge_cum = hedge_cum.loc[common_idx]
                    hedge_metrics = compute_metrics(hedge_returns.loc[common_idx], "含对冲")
                    metrics_list.append(hedge_metrics)
                    metrics_df = pd.DataFrame(metrics_list)

        progress.progress(85, text="⚡ 正在进行压力测试...")

        # 压力测试
        selected_stress = st.session_state.selected_stress
        selected_events = {
            k: STRESS_EVENTS[k] for k in selected_stress if k in STRESS_EVENTS
        }
        stress_df = pd.DataFrame()
        if selected_events:
            stress_df = stress_test(portfolio_returns, benchmark_returns, selected_events)

        progress.progress(100, text="✅ 完成！")
        progress.empty()

        # 保存结果到 session state
        st.session_state.backtest_results = {
            "metrics_df": metrics_df,
            "portfolio_cum": portfolio_cum,
            "benchmark_cum": benchmark_cum,
            "hedge_cum": hedge_cum,
            "portfolio_returns": portfolio_returns,
            "benchmark_returns": benchmark_returns,
            "stress_df": stress_df,
            "tickers_str": tickers_str,
            "weights_str": weights_str,
            "start_date_str": start_date_str,
            "rebalance": rebalance,
            "bench_str": bench_str,
            "bench_w_str": bench_w_str,
        }

    # --- 显示结果 ---
    results = st.session_state.backtest_results
    if results is not None:
        st.markdown("---")
        st.header("📊 回测结果")

        # 绩效指标表
        st.subheader("📋 绩效指标")
        st.dataframe(results["metrics_df"], width="stretch", hide_index=True)

        # 结果标签页
        rtab1, rtab2, rtab3, rtab4, rtab5 = st.tabs([
            "📈 权益曲线",
            "📉 回撤分析",
            "📊 年度 & 月度收益",
            "⚡ 压力测试",
            "📥 下载报告",
        ])

        with rtab1:
            st.subheader("权益曲线")
            fig_eq = plot_equity_curve(
                results["portfolio_cum"],
                results["benchmark_cum"],
                results["hedge_cum"],
            )
            st.plotly_chart(fig_eq, width="stretch")

        with rtab2:
            st.subheader("回撤分析")
            fig_dd = plot_drawdown(
                results["portfolio_returns"], results["benchmark_returns"]
            )
            st.plotly_chart(fig_dd, width="stretch")

        with rtab3:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("年度收益")
                fig_ar = plot_annual_returns(
                    results["portfolio_returns"], results["benchmark_returns"]
                )
                st.plotly_chart(fig_ar, width="stretch")
            with col_b:
                st.subheader("月度收益热力图")
                fig_hm = plot_monthly_heatmap(results["portfolio_returns"])
                st.plotly_chart(fig_hm, width="stretch")

        with rtab4:
            st.subheader("压力测试")
            if not results["stress_df"].empty:
                st.dataframe(results["stress_df"], width="stretch", hide_index=True)
                fig_stress = plot_stress_test(results["stress_df"])
                st.plotly_chart(fig_stress, width="stretch")
            else:
                st.info(
                    "未选择压力测试事件或无可用数据。前往 ⚙️ 设置 添加压力测试事件。"
                )

        with rtab5:
            st.subheader("下载完整报告")
            config_info = {
                "tickers": results["tickers_str"],
                "weights": results["weights_str"],
                "start": results["start_date_str"],
                "rebalance": results["rebalance"],
                "benchmark": results.get("bench_str", "N/A"),
            }
            report_html = generate_html_report(
                results["metrics_df"],
                results["portfolio_cum"],
                results["benchmark_cum"],
                results["hedge_cum"],
                results["portfolio_returns"],
                results["benchmark_returns"],
                results["portfolio_returns"],
                results["stress_df"],
                config_info,
            )
            st.download_button(
                label="📥 下载 HTML 报告",
                data=report_html,
                file_name=f"backtest_report_{dt.date.today()}.html",
                mime="text/html",
                width="stretch",
            )
            st.markdown("报告包含所有图表和指标，可直接在浏览器中打开查看。")

    else:
        # 还没有运行过回测
        st.markdown("---")
        st.info("👆 配置好资产和基准后，点击 **🚀 运行回测** 开始。")

        st.markdown("""
        ### 💡 快速开始
        1. 在 **我的组合** 区配置投资资产（浏览或搜索）
        2. 在 **参考基准** 区配置基准资产（支持多资产加权）
        3. 选择合适的回测参数（在 ⚙️ 设置 标签页）
        4. 点击 **🚀 运行回测**

        ### 🌍 支持的市场
        | 市场 | 说明 |
        |------|------|
        | 🇨🇳 A股 | 沪深指数、ETF、个股 |
        | 🇭🇰 港股 | 腾讯、阿里等个股 |
        | 🇺🇸 美股 | 标普500、纳指、个股、商品ETF |
        | 🇯🇵 日本 | 日经225、东证指数 |
        | 🇪🇺 欧洲 | 德国DAX、英国富时100、法国CAC40 |
        | ₿ 加密货币 | BTC、ETH、SOL 等 |
        """)


# ============================================================
# Tab 2: ⚙️ 设置
# ============================================================
with tab_settings:
    st.subheader("⚙️ 系统设置")

    # --- 回测设置 ---
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)
    st.markdown("### 📅 回测参数")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "回测起始日期",
            value=st.session_state.start_date,
            min_value=dt.date(2000, 1, 1),
            max_value=dt.date.today() - dt.timedelta(days=30),
            key="set_start_date",
        )
    with col2:
        rebalance = st.selectbox(
            "再平衡频率",
            ["无", "每月", "每季度"],
            index=["无", "每月", "每季度"].index(st.session_state.rebalance),
            help="无：不进行再平衡；每月/每季度：按指定频率重新调整权重",
            key="set_rebalance",
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- 压力测试 ---
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)
    st.markdown("### ⚡ 压力测试事件")
    st.markdown("选择要分析的历史压力事件。")

    stress_options = list(STRESS_EVENTS.keys())
    selected_stress = st.multiselect(
        "选择压力测试事件",
        stress_options,
        default=st.session_state.selected_stress,
        key="set_stress",
    )

    # 显示事件详情
    if selected_stress:
        event_details = []
        for name in selected_stress:
            info = STRESS_EVENTS[name]
            event_details.append(
                {
                    "事件": name,
                    "时间范围": f"{info['start']} ~ {info['end']}",
                    "描述": info.get("desc", ""),
                }
            )
        st.dataframe(pd.DataFrame(event_details), width="stretch", hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # --- 对冲配置 ---
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)
    st.markdown("### 🛡️ 对冲配置（可选）")
    st.markdown("添加对冲资产后，回测结果将额外显示含对冲的组合表现。")

    hedge_enabled = st.checkbox(
        "启用对冲资产", value=st.session_state.hedge_enabled, key="set_hedge_enabled"
    )

    if hedge_enabled:
        col1, col2 = st.columns(2)
        with col1:
            hedge_ticker = st.text_input(
                "对冲资产 Ticker",
                value=st.session_state.hedge_ticker,
                help="如 GLD、sh518880（黄金ETF）",
                key="set_hedge_ticker",
            )
        with col2:
            hedge_weight = st.slider(
                "对冲比例",
                0.0,
                0.5,
                value=st.session_state.hedge_weight,
                step=0.05,
                help="从主组合中分配给对冲资产的比例",
                key="set_hedge_weight",
            )
    st.markdown("</div>", unsafe_allow_html=True)

    # --- 保存设置 ---
    st.markdown("")
    if st.button("💾 保存设置", type="primary", width="stretch", key="save_settings"):
        st.session_state.start_date = start_date
        st.session_state.rebalance = rebalance
        st.session_state.selected_stress = selected_stress
        st.session_state.hedge_enabled = hedge_enabled
        if hedge_enabled:
            st.session_state.hedge_ticker = st.session_state.get(
                "set_hedge_ticker", "sh518880"
            )
            st.session_state.hedge_weight = st.session_state.get(
                "set_hedge_weight", 0.1
            )
        st.success("✅ 设置已保存！")

    # --- 数据管理 ---
    st.markdown("---")
    st.markdown("### 🗂️ 数据管理")
    col1, col2 = st.columns(2)
    with col1:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        if os.path.exists(data_dir):
            cache_files = os.listdir(data_dir)
            cache_count = len(cache_files)
            cache_size = (
                sum(os.path.getsize(os.path.join(data_dir, f)) for f in cache_files)
                / (1024 * 1024)
            )
            st.metric("缓存文件数", cache_count)
            st.metric("缓存大小", f"{cache_size:.1f} MB")
        else:
            st.info("暂无缓存数据")
    with col2:
        if st.button("🗑️ 清除所有缓存", key="clear_cache"):
            import shutil

            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
                os.makedirs(data_dir)
                st.success("✅ 缓存已清除！")
                st.rerun()


# ============================================================
# 页脚
# ============================================================
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #999; font-size: 12px;">'
    "📊 投资组合回测器 v5 · 数据源: AKShare / yfinance · 仅供学习研究，不构成投资建议"
    "</div>",
    unsafe_allow_html=True,
)