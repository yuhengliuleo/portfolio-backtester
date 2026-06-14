"""
Streamlit 投资组合回测应用 v3
===============================
- 手动输入 Ticker + 权重
- AKShare 数据源（免费，覆盖 A股/港股/美股/ETF）
- 压力测试、对冲分析、绩效指标、交互式 Plotly 图表
- 生成完整 HTML 报告
- pyfolio-reloaded tearsheet（可选）
"""

import os
import sys
import datetime as dt
import warnings

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

# 确保当前目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import (
    STRESS_EVENTS,
    ASSET_NAME_TO_TICKER,
    download_data,
    calculate_portfolio_returns,
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
)

# ============================================================
# Streamlit 页面配置
# ============================================================
st.set_page_config(
    page_title="投资组合回测器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# 自定义 CSS
# ============================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1f77b4;
        text-align: center;
        padding: 0.5rem 0;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 1.5rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.1rem;
    }
    .setting-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
    .info-box {
        background: #e8f4fd;
        border-left: 4px solid #1f77b4;
        padding: 0.8rem 1rem;
        border-radius: 0 6px 6px 0;
        margin: 0.5rem 0;
    }
    .ticker-chip {
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        padding: 4px 12px;
        border-radius: 16px;
        margin: 3px 4px;
        font-size: 0.85rem;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# Session State 初始化
# ============================================================
defaults = {
    "tickers_str": "sh000300, sh518880, sh511010",
    "weights_str": "0.5, 0.3, 0.2",
    "start_date": dt.date(2018, 1, 1),
    "rebalance": "每月",
    "benchmark_input": "sh000300",
    "selected_stress": ["2020-COVID", "2022-熊市"],
    "hedge_enabled": False,
    "hedge_ticker": "sh518880",
    "hedge_weight": 0.1,
    "backtest_results": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 标题
# ============================================================
st.markdown('<div class="main-header">📊 投资组合回测器</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">多资产组合回测 · 压力测试 · 对冲分析 · 交互式图表 · 报告导出</div>',
    unsafe_allow_html=True,
)

# ============================================================
# 标签页：回测 / 设置
# ============================================================
tab_backtest, tab_settings = st.tabs(["📊 回测", "⚙️ 设置"])


# ============================================================
# Tab 1: 📊 回测
# ============================================================
with tab_backtest:
    # --- 输入区域 ---
    st.subheader("📦 资产配置")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        tickers_str = st.text_input(
            "Tickers（逗号分隔）",
            value=st.session_state.tickers_str,
            help="示例：sh000300（沪深300）、SPY（标普500）、00700（腾讯）、AAPL（苹果）",
            key="input_tickers",
        )
    with col2:
        weights_str = st.text_input(
            "权重（总和≈1）",
            value=st.session_state.weights_str,
            help="与 Tickers 一一对应",
            key="input_weights",
        )
    
    # 常用资产速查
    with st.expander("🏷️ 常用资产速查", expanded=False):
        quick_assets = {
            "A股指数": ["sh000300 沪深300", "sh000905 中证500", "sh000016 上证50", "sz399006 创业板"],
            "A股 ETF": ["sh510300 沪深300ETF", "sh518880 黄金ETF", "sh511010 国债ETF", "sh513100 纳指ETF"],
            "美股": ["SPY 标普500", "QQQ 纳指100", "GLD 黄金", "TLT 长期国债"],
            "港股": ["00700 腾讯", "09988 阿里", "03690 美团", "01211 比亚迪"],
        }
        cols = st.columns(len(quick_assets))
        for col, (market, assets) in zip(cols, quick_assets.items()):
            with col:
                st.markdown(f"**{market}**")
                for asset in assets:
                    st.caption(asset)
    
    st.markdown("---")
    
    # --- 运行按钮 ---
    run_backtest = st.button("🚀 运行回测", type="primary", use_container_width=True, key="run_bt")
    
    if run_backtest:
        # 解析输入
        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        try:
            weights = [float(w.strip()) for w in weights_str.split(",") if w.strip()]
        except ValueError:
            st.error("❌ 权重格式错误，请输入数字，如：0.4, 0.2, 0.2, 0.2")
            st.stop()

        if len(tickers) == 0:
            st.error("❌ 请至少输入一个 Ticker")
            st.stop()

        if len(tickers) != len(weights):
            st.error(f"❌ Tickers 数量（{len(tickers)}）与权重数量（{len(weights)}）不匹配")
            st.stop()

        weight_sum = sum(weights)
        if abs(weight_sum - 1.0) > 0.05:
            st.warning(f"⚠️ 权重总和为 {weight_sum:.3f}，不接近 1。将自动归一化。")
            weights = [w / weight_sum for w in weights]

        # 进度条
        progress = st.progress(0, text="📥 正在下载数据...")

        # 获取设置
        start_date = st.session_state.start_date
        rebalance = st.session_state.rebalance
        benchmark_input = st.session_state.benchmark_input

        end_date_str = dt.date.today().strftime("%Y-%m-%d")
        start_date_str = start_date.strftime("%Y-%m-%d") if isinstance(start_date, dt.date) else str(start_date)

        prices, invalid_tickers = download_data(tickers, start_date_str, end_date_str)

        if invalid_tickers:
            st.warning(f"⚠️ 以下 Ticker 下载失败或无数据: {', '.join(invalid_tickers)}")
            valid_pairs = [(t, w) for t, w in zip(tickers, weights) if t not in invalid_tickers]
            if valid_pairs:
                tickers, weights = zip(*valid_pairs)
                tickers, weights = list(tickers), list(weights)
                ws = sum(weights)
                weights = [w / ws for w in weights]
                prices = prices[tickers]
            else:
                st.error("❌ 所有 Ticker 均下载失败，无法执行回测")
                st.stop()

        progress.progress(20, text="📥 正在下载基准数据...")

        benchmark_prices, benchmark_invalid = download_data([benchmark_input], start_date_str, end_date_str)
        has_benchmark = benchmark_input not in benchmark_invalid and not benchmark_prices.empty
        if not has_benchmark:
            st.warning(f"⚠️ 基准指数 {benchmark_input} 下载失败，将不显示基准对比")

        progress.progress(40, text="📊 正在计算组合收益...")

        portfolio_returns = calculate_portfolio_returns(prices, weights, rebalance)
        portfolio_cum = (1 + portfolio_returns).cumprod()

        benchmark_returns = None
        benchmark_cum = None
        if has_benchmark:
            benchmark_returns = calculate_benchmark_returns(benchmark_prices.iloc[:, 0])
            benchmark_cum = (1 + benchmark_returns).cumprod()
            common_idx = portfolio_cum.index.intersection(benchmark_cum.index)
            portfolio_cum = portfolio_cum.loc[common_idx]
            benchmark_cum = benchmark_cum.loc[common_idx]
            portfolio_returns = portfolio_returns.loc[common_idx]
            benchmark_returns = benchmark_returns.loc[common_idx]

        progress.progress(60, text="📊 正在计算绩效指标...")

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

        progress.progress(80, text="⚡ 正在进行压力测试...")

        selected_stress = st.session_state.selected_stress
        selected_events = {k: STRESS_EVENTS[k] for k in selected_stress if k in STRESS_EVENTS}
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
            "benchmark_input": benchmark_input,
        }
    
    # --- 显示结果 ---
    results = st.session_state.backtest_results
    if results is not None:
        st.markdown("---")
        st.header("📊 回测结果")

        # 绩效指标表
        st.subheader("📋 绩效指标")
        st.dataframe(results["metrics_df"], use_container_width=True, hide_index=True)

        # 结果标签页
        rtab1, rtab2, rtab3, rtab4, rtab5 = st.tabs([
            "📈 权益曲线", "📉 回撤分析", "📊 年度 & 月度收益", "⚡ 压力测试", "📥 下载报告"
        ])

        with rtab1:
            st.subheader("权益曲线")
            fig_eq = plot_equity_curve(results["portfolio_cum"], results["benchmark_cum"], results["hedge_cum"])
            st.plotly_chart(fig_eq, use_container_width=True)

        with rtab2:
            st.subheader("回撤分析")
            fig_dd = plot_drawdown(results["portfolio_returns"], results["benchmark_returns"])
            st.plotly_chart(fig_dd, use_container_width=True)

        with rtab3:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("年度收益")
                fig_ar = plot_annual_returns(results["portfolio_returns"], results["benchmark_returns"])
                st.plotly_chart(fig_ar, use_container_width=True)
            with col_b:
                st.subheader("月度收益热力图")
                fig_hm = plot_monthly_heatmap(results["portfolio_returns"])
                st.plotly_chart(fig_hm, use_container_width=True)

        with rtab4:
            st.subheader("压力测试")
            if not results["stress_df"].empty:
                st.dataframe(results["stress_df"], use_container_width=True, hide_index=True)
                fig_stress = plot_stress_test(results["stress_df"])
                st.plotly_chart(fig_stress, use_container_width=True)
            else:
                st.info("未选择压力测试事件或无可用数据。前往 ⚙️ 设置 添加压力测试事件。")

        with rtab5:
            st.subheader("下载完整报告")
            config_info = {
                "tickers": results["tickers_str"],
                "weights": results["weights_str"],
                "start": results["start_date_str"],
                "rebalance": results["rebalance"],
                "benchmark": results["benchmark_input"],
            }
            report_html = generate_html_report(
                results["metrics_df"], results["portfolio_cum"], results["benchmark_cum"],
                results["hedge_cum"], results["portfolio_returns"], results["benchmark_returns"],
                results["portfolio_returns"], results["stress_df"], config_info,
            )
            st.download_button(
                label="📥 下载 HTML 报告",
                data=report_html,
                file_name=f"backtest_report_{dt.date.today()}.html",
                mime="text/html",
                use_container_width=True,
            )
            st.markdown("报告包含所有图表和指标，可直接在浏览器中打开查看。")
    
    else:
        # 还没有运行过回测
        st.markdown("---")
        st.info("👆 配置好 Ticker 和权重后，点击 **🚀 运行回测** 开始。")
        
        st.markdown("""
        ### 💡 快速开始
        1. 在上方输入 Tickers（如 `sh000300, sh518880`）和对应权重（如 `0.7, 0.3`）
        2. 点击 **🚀 运行回测**
        3. 查看权益曲线、回撤、压力测试等结果
        """)


# ============================================================
# Tab 2: ⚙️ 设置
# ============================================================
with tab_settings:
    st.subheader("⚙️ 系统设置")
    
    # --- 回测设置 ---
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)
    st.markdown("### 📅 回测设置")
    
    col1, col2, col3 = st.columns(3)
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
    with col3:
        benchmark_input = st.text_input(
            "基准指数",
            value=st.session_state.benchmark_input,
            help="默认沪深300，可改为 SPY、QQQ 等",
            key="set_benchmark",
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
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
            event_details.append({
                "事件": name,
                "时间范围": f"{info['start']} ~ {info['end']}",
                "描述": info.get("desc", ""),
            })
        st.dataframe(pd.DataFrame(event_details), use_container_width=True, hide_index=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # --- 对冲配置 ---
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)
    st.markdown("### 🛡️ 对冲配置（可选）")
    st.markdown("添加对冲资产后，回测结果将额外显示含对冲的组合表现。")
    
    hedge_enabled = st.checkbox("启用对冲资产", value=st.session_state.hedge_enabled, key="set_hedge_enabled")
    
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
                0.0, 0.5,
                value=st.session_state.hedge_weight,
                step=0.05,
                help="从主组合中分配给对冲资产的比例",
                key="set_hedge_weight",
            )
    st.markdown('</div>', unsafe_allow_html=True)
    
    # --- 保存设置 ---
    st.markdown("")
    if st.button("💾 保存设置", type="primary", use_container_width=True, key="save_settings"):
        st.session_state.start_date = start_date
        st.session_state.rebalance = rebalance
        st.session_state.benchmark_input = benchmark_input
        st.session_state.selected_stress = selected_stress
        st.session_state.hedge_enabled = hedge_enabled
        if hedge_enabled:
            st.session_state.hedge_ticker = st.session_state.get("set_hedge_ticker", "sh518880")
            st.session_state.hedge_weight = st.session_state.get("set_hedge_weight", 0.1)
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
            cache_size = sum(os.path.getsize(os.path.join(data_dir, f)) for f in cache_files) / (1024 * 1024)
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
    '📊 投资组合回测器 v3 · 数据源: AKShare · 仅供学习研究，不构成投资建议'
    '</div>',
    unsafe_allow_html=True,
)