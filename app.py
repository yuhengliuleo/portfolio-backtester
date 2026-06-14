"""
Streamlit 投资组合回测应用 v4
===============================
- 双模式资产选择：📂 级联浏览（市场→类型→标的）/ 🔍 模糊搜索
- AKShare 数据源（免费，覆盖 A股/港股/美股/ETF/日本/欧洲）
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
    ASSET_CATALOG,
    ASSET_NAME_TO_TICKER,
    ASSET_LABEL_TO_TICKER,
    get_asset_options,
    search_assets,
    get_assets_by_market,
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
    .weight-ok { color: #2e7d32; font-weight: 600; }
    .weight-warn { color: #e65100; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 辅助函数
# ============================================================
MARKETS = list(ASSET_CATALOG.keys())  # 全局市场列表


def _find_asset_by_ticker(ticker: str) -> dict:
    """通过 ticker 反查市场和类型"""
    for mkt, types in ASSET_CATALOG.items():
        for typ, assets in types.items():
            for name, tkr in assets.items():
                if tkr == ticker:
                    return {"market": mkt, "type": typ, "name": name}
    return {"market": MARKETS[0], "type": "", "name": ""}


def _get_uid() -> str:
    """生成行的唯一 ID，用于稳定的 widget key"""
    counter = st.session_state.get("_uid_counter", 0)
    st.session_state["_uid_counter"] = counter + 1
    return f"r{counter}"


# ============================================================
# Session State 初始化（资产行）
# ============================================================
if "asset_rows" not in st.session_state:
    st.session_state.asset_rows = [
        {"uid": "init0", "mode": "browse", "market": "🇨🇳 A股", "type": "ETF",
         "ticker": "sh510300", "weight": 40, "search_text": ""},
        {"uid": "init1", "mode": "browse", "market": "🇺🇸 美股", "type": "指数",
         "ticker": "SPY", "weight": 40, "search_text": ""},
        {"uid": "init2", "mode": "browse", "market": "🇽 黄金", "type": "大宗商品",
         "ticker": "sh518880", "weight": 20, "search_text": ""},
    ]
    st.session_state["_uid_counter"] = 10

# 其他默认设置
defaults = {
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
    # --- 动态资产配置（双模式：📂 浏览 / 🔍 搜索） ---
    st.subheader("📦 资产配置")

    rows_to_delete: list[int] = []

    for i, row in enumerate(st.session_state.asset_rows):
        # 确保每行有 uid
        if "uid" not in row:
            row["uid"] = _get_uid()
        uid = row["uid"]

        # 确保新字段存在（向后兼容旧格式）
        if "mode" not in row:
            row["mode"] = "browse"
        if "market" not in row or "type" not in row:
            info = _find_asset_by_ticker(row.get("ticker", ""))
            row["market"] = info["market"]
            row["type"] = info["type"]
        if "search_text" not in row:
            row["search_text"] = ""

        # ---- 行布局 ----
        mode_col, content_col, weight_col, del_col = st.columns(
            [0.8, 5.7, 1.5, 0.5]
        )

        # ---- 模式切换 ----
        with mode_col:
            mode_choice = st.radio(
                "模式",
                ["📂 浏览", "🔍 搜索"],
                index=0 if row["mode"] == "browse" else 1,
                key=f"mode_{uid}",
                horizontal=True,
                label_visibility="collapsed",
            )
            new_mode = "browse" if "浏览" in mode_choice else "search"

            # 模式切换时重置相关内容
            if new_mode != row["mode"]:
                row["mode"] = new_mode
                if new_mode == "browse":
                    info = _find_asset_by_ticker(row.get("ticker", ""))
                    row["market"] = info["market"]
                    row["type"] = info["type"]
                    row["search_text"] = ""
                else:
                    row["search_text"] = ""
                st.rerun()

        # ---- 资产选择 ----
        with content_col:
            if row["mode"] == "browse":
                # ========== 级联浏览模式：市场 → 类型 → 标的 ==========
                bc1, bc2, bc3 = st.columns(3)

                # 第1级：市场
                with bc1:
                    sel_market = row.get("market", MARKETS[0])
                    try:
                        mkt_idx = MARKETS.index(sel_market)
                    except ValueError:
                        mkt_idx = 0
                    sel_market = st.selectbox(
                        "市场", MARKETS, index=mkt_idx,
                        key=f"mkt_{uid}", label_visibility="collapsed",
                    )

                # 市场变化时重置下游
                prev_mkt = st.session_state.get(f"_pmkt_{uid}", "")
                if prev_mkt != sel_market:
                    for _k in [f"typ_{uid}", f"ast_{uid}"]:
                        if _k in st.session_state:
                            del st.session_state[_k]
                    st.session_state[f"_pmkt_{uid}"] = sel_market

                # 第2级：类型
                types_list = list(ASSET_CATALOG.get(sel_market, {}).keys())
                with bc2:
                    sel_type = row.get("type", "")
                    try:
                        typ_idx = types_list.index(sel_type)
                    except (ValueError, IndexError):
                        typ_idx = 0
                    if types_list:
                        sel_type = st.selectbox(
                            "类型", types_list, index=typ_idx,
                            key=f"typ_{uid}", label_visibility="collapsed",
                        )
                    else:
                        sel_type = ""
                        st.caption("无可选类型")

                # 类型变化时重置标的
                prev_typ = st.session_state.get(f"_ptyp_{uid}", "")
                if prev_typ != sel_type:
                    if f"ast_{uid}" in st.session_state:
                        del st.session_state[f"ast_{uid}"]
                    st.session_state[f"_ptyp_{uid}"] = sel_type

                # 第3级：标的
                assets_dict = ASSET_CATALOG.get(sel_market, {}).get(sel_type, {})
                asset_names = list(assets_dict.keys())
                with bc3:
                    if asset_names:
                        cur_ticker = row.get("ticker", "")
                        ast_idx = 0
                        for a_i, nm in enumerate(asset_names):
                            if assets_dict.get(nm) == cur_ticker:
                                ast_idx = a_i
                                break
                        sel_name = st.selectbox(
                            "标的", asset_names, index=ast_idx,
                            key=f"ast_{uid}", label_visibility="collapsed",
                        )
                        row["ticker"] = assets_dict.get(sel_name, "")
                    else:
                        row["ticker"] = ""
                        st.caption("无可选标的")

                row["market"] = sel_market
                row["type"] = sel_type

            else:
                # ========== 搜索模式：输入关键词 → 从结果中选择 ==========
                sc1, sc2 = st.columns([2, 3])

                with sc1:
                    kw = st.text_input(
                        "搜索",
                        value=row.get("search_text", ""),
                        placeholder="代码或名称 (如 AAPL, 黄金, 沪深300)...",
                        key=f"kw_{uid}",
                        label_visibility="collapsed",
                    )
                    row["search_text"] = kw

                with sc2:
                    if kw and kw.strip():
                        results = search_assets(kw.strip())
                        if results:
                            opts = [
                                f"{r['name']} ({r['ticker']}) — {r['market']} · {r['type']}"
                                for r in results
                            ]
                            # 尝试匹配当前 ticker
                            r_idx = 0
                            cur_tkr = row.get("ticker", "")
                            for r_i, r in enumerate(results):
                                if r["ticker"] == cur_tkr:
                                    r_idx = r_i
                                    break
                            sel = st.selectbox(
                                "搜索结果", opts, index=r_idx,
                                key=f"res_{uid}", label_visibility="collapsed",
                            )
                            chosen = results[opts.index(sel)]
                            row["ticker"] = chosen["ticker"]
                            row["market"] = chosen["market"]
                            row["type"] = chosen["type"]
                        else:
                            st.caption("❌ 未找到匹配资产")
                    else:
                        st.caption("💡 输入关键词搜索资产")

        # ---- 权重 ----
        with weight_col:
            row["weight"] = st.number_input(
                f"权重_{uid}", 0.0, 100.0, float(row["weight"]),
                step=5.0, key=f"w_{uid}", label_visibility="collapsed",
            )

        # ---- 删除 ----
        with del_col:
            if st.button("🗑️", key=f"del_{uid}", help="删除此资产"):
                rows_to_delete.append(i)

    # 删除标记的行
    for idx in sorted(rows_to_delete, reverse=True):
        st.session_state.asset_rows.pop(idx)
        st.rerun()

    # ---- 添加按钮 + 权重合计 ----
    col_add, col_sum = st.columns([1, 3])
    with col_add:
        if st.button("➕ 添加资产", width="stretch"):
            new_uid = _get_uid()
            st.session_state.asset_rows.append({
                "uid": new_uid,
                "mode": "browse",
                "market": MARKETS[0],
                "type": list(ASSET_CATALOG.get(MARKETS[0], {}).keys())[0] if ASSET_CATALOG.get(MARKETS[0]) else "",
                "ticker": "",
                "weight": 10,
                "search_text": "",
            })
            st.rerun()

    with col_sum:
        total_weight = sum(r["weight"] for r in st.session_state.asset_rows)
        if abs(total_weight - 100) < 1:
            st.markdown(
                f"<span class='weight-ok'>✅ 权重合计：{total_weight:.0f}%</span>",
                unsafe_allow_html=True,
            )
        elif total_weight == 0:
            st.markdown(
                f"<span class='weight-warn'>⚠️ 权重合计：0%</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<span class='weight-warn'>⚠️ 权重合计：{total_weight:.0f}%（将自动归一化）</span>",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # --- 运行按钮 ---
    run_backtest = st.button("🚀 运行回测", type="primary", width="stretch", key="run_bt")

    if run_backtest:
        # 从 asset_rows 提取 tickers 和 weights
        asset_rows = st.session_state.asset_rows
        tickers = [r["ticker"] for r in asset_rows if r.get("ticker")]
        weights = [r["weight"] / 100.0 for r in asset_rows if r.get("ticker")]  # 百分比转小数

        if len(tickers) == 0:
            st.error("❌ 请至少添加一个资产")
            st.stop()

        if len(tickers) != len(weights):
            st.error(f"❌ Tickers 数量（{len(tickers)}）与权重数量（{len(weights)}）不匹配")
            st.stop()

        weight_sum = sum(weights)
        if abs(weight_sum - 1.0) > 0.05:
            st.warning(f"⚠️ 权重总和为 {weight_sum:.3f}，将自动归一化。")
            weights = [w / weight_sum for w in weights]

        # 构建显示用的字符串
        tickers_str = ", ".join(tickers)
        weights_str = ", ".join(f"{w:.2f}" for w in weights)

        # 进度条
        progress = st.progress(0, text="📥 正在下载数据...")

        # 获取设置
        start_date = st.session_state.start_date
        rebalance = st.session_state.rebalance
        benchmark_input = st.session_state.benchmark_input

        end_date_str = dt.date.today().strftime("%Y-%m-%d")
        start_date_str = (
            start_date.strftime("%Y-%m-%d")
            if isinstance(start_date, dt.date)
            else str(start_date)
        )

        prices, invalid_tickers = download_data(tickers, start_date_str, end_date_str)

        if invalid_tickers:
            st.warning(f"⚠️ 以下 Ticker 下载失败或无数据: {', '.join(invalid_tickers)}")
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

        progress.progress(20, text="📥 正在下载基准数据...")

        benchmark_prices, benchmark_invalid = download_data(
            [benchmark_input], start_date_str, end_date_str
        )
        has_benchmark = (
            benchmark_input not in benchmark_invalid and not benchmark_prices.empty
        )
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
            "benchmark_input": benchmark_input,
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
                "benchmark": results["benchmark_input"],
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
        st.info("👆 配置好资产和权重后，点击 **🚀 运行回测** 开始。")

        st.markdown("""
        ### 💡 快速开始
        1. 在资产配置区，选择 **📂 浏览** 逐级选择（市场 → 类型 → 标的），或切换 **🔍 搜索** 输入关键词
        2. 设置各项权重
        3. 点击 **🚀 运行回测**
        4. 查看权益曲线、回撤、压力测试等结果

        ### 🌍 支持的市场
        | 市场 | 说明 |
        |------|------|
        | 🇨🇳 A股 | 沪深指数、ETF |
        | 🇭🇰 港股 | 腾讯、阿里等个股 |
        | 🇺🇸 美股 | 标普500、纳指、个股、商品ETF |
        | 🇯🇵 日本 | 日经225、东证指数 |
        | 🇪🇺 欧洲 | 德国DAX、英国富时100、法国CAC40 |
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
            help="默认沪深300（sh000300），可改为 SPY、QQQ 等",
            key="set_benchmark",
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
        st.session_state.benchmark_input = benchmark_input
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
    "📊 投资组合回测器 v4 · 数据源: AKShare · 仅供学习研究，不构成投资建议"
    "</div>",
    unsafe_allow_html=True,
)