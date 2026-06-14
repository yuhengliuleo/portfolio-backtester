"""
📊 投资组合回测器 v3
====================
三大标签页：🤖 AI 对话 · 📊 回测 · ⚙️ 设置
数据源：AKShare（免费，覆盖全球市场）
AI 解析：通用 OpenAI 兼容 API
"""

import os
import sys
import datetime as dt
import streamlit as st
import pandas as pd

# 确保能导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import (
    download_data, calculate_portfolio_returns, calculate_benchmark_returns,
    compute_metrics, stress_test, STRESS_EVENTS,
    plot_equity_curve, plot_drawdown, plot_monthly_heatmap,
    plot_annual_returns, plot_stress_test,
    calculate_hedge_portfolio, generate_html_report, parse_portfolio_with_ai,
    test_ai_connection, ASSET_NAME_TO_TICKER, detect_market,
)

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="📊 投资组合回测器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# Session State 初始化
# ============================================================
def init_session():
    """初始化所有 session state 默认值"""
    defaults = {
        # AI 配置
        "ai_base_url": "https://api.openai.com/v1",
        "ai_api_key": "",
        "ai_model": "gpt-4o-mini",
        # 回测配置
        "tickers_str": "sh000300, sh510500, sh518880, sh511010",
        "weights_str": "0.4, 0.2, 0.2, 0.2",
        "start_date": dt.date(2018, 1, 1),
        "rebalance": "无",
        "benchmark_input": "sh000300",
        # 压力测试
        "selected_stress": ["2020-COVID", "2022-熊市"],
        # 对冲
        "hedge_enabled": False,
        "hedge_ticker": "sh518880",
        "hedge_weight": 0.1,
        # AI 聊天记录（持久化）
        "chat_history": [],
        # 回测结果
        "backtest_results": None,
        # 标签页
        "active_tab": "📊 回测",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session()


# ============================================================
# 自定义 CSS
# ============================================================
st.markdown("""
<style>
    /* 隐藏默认 header 和 footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 美化标签页 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 24px;
        border-radius: 8px 8px 0 0;
        font-size: 16px;
        font-weight: 600;
    }
    
    /* 聊天气泡样式 */
    .chat-user {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 12px 18px;
        border-radius: 18px 18px 4px 18px;
        margin: 8px 0;
        max-width: 80%;
        float: right;
        clear: both;
    }
    .chat-ai {
        background: #f0f2f6;
        color: #333;
        padding: 12px 18px;
        border-radius: 18px 18px 18px 4px;
        margin: 8px 0;
        max-width: 80%;
        float: left;
        clear: both;
    }
    .chat-container {
        overflow: hidden;
        margin-bottom: 16px;
    }
    
    /* 快捷按钮 */
    .quick-btn {
        display: inline-block;
        padding: 6px 14px;
        margin: 4px;
        border-radius: 16px;
        background: #e8eaf6;
        color: #333;
        font-size: 13px;
        cursor: pointer;
        border: 1px solid #c5cae9;
    }
    .quick-btn:hover {
        background: #c5cae9;
    }
    
    /* 设置页面卡片 */
    .setting-card {
        background: #fafafa;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 标题
# ============================================================
st.title("📊 投资组合回测器")
st.caption("数据源：AKShare（A股/港股/美股/ETF） · AI 自然语言配置 · 压力测试 · 对冲分析")


# ============================================================
# 三大标签页
# ============================================================
tab_chat, tab_backtest, tab_settings = st.tabs([
    "🤖 AI 对话", "📊 回测", "⚙️ 设置"
])


# ============================================================
# Tab 1: 🤖 AI 对话
# ============================================================

def get_ai_config():
    """获取当前 AI 配置（优先读取设置页面 widget 的值，兼容用户未点保存的情况）"""
    base_url = st.session_state.get("set_ai_base_url") or st.session_state.get("ai_base_url", "")
    api_key = st.session_state.get("set_ai_api_key") or st.session_state.get("ai_api_key", "")
    model = st.session_state.get("set_ai_model") or st.session_state.get("ai_model", "")
    return base_url, api_key, model

with tab_chat:
    # 检查 AI 是否已配置（直接读取设置页面 widget 的 key，无需先点保存）
    _ai_url, _ai_key, _ai_model = get_ai_config()
    ai_configured = bool(_ai_url and _ai_key and _ai_model)
    
    if not ai_configured:
        st.info("🔑 尚未配置 AI。请前往 **⚙️ 设置** 标签页配置 AI API，即可使用自然语言描述你的投资组合。")
        st.markdown("### 💡 不用 AI 也能用！")
        st.markdown("直接前往 **📊 回测** 标签页，手动输入 Ticker 和权重即可运行回测。")
        
        st.markdown("---")
        st.markdown("### 📖 使用说明")
        st.markdown("""
        **配置 AI 后可以：**
        - 用自然语言描述投资需求，AI 自动解析为资产配置
        - 示例输入：
            - `帮我配一个 60% 标普500 + 30% 黄金 + 10% 美债`
            - `我想要稳健配置，沪深300 40%、中证500 20%、国债ETF 30%、黄金ETF 10%`
            - `激进成长型：纳指100 50%、英伟达 20%、比特币 15%、黄金 15%`
        
        **支持的市场：** A股、港股、美股、ETF
        **常见资产代码：** SPY（标普500）、QQQ（纳指100）、GLD（黄金）、TLT（长债）、sh000300（沪深300）...
        """)
    else:
        st.success(f"✅ AI 已连接 — 使用模型: **{_ai_model}**")
        
        # 显示聊天历史
        if st.session_state.chat_history:
            for msg in st.session_state.chat_history:
                role = msg["role"]
                content = msg["content"]
                if role == "user":
                    st.markdown(f'<div class="chat-container"><div class="chat-user">🧑 {content}</div></div>', unsafe_allow_html=True)
                else:
                    # AI 回复可能包含表格数据
                    if isinstance(content, dict):
                        # 包含解析结果
                        st.markdown(f'<div class="chat-container"><div class="chat-ai">🤖 {content.get("message", "")}</div></div>', unsafe_allow_html=True)
                        if "config" in content:
                            df = pd.DataFrame(content["config"])
                            st.dataframe(df, use_container_width=True, hide_index=True)
                            st.info("👆 已自动填入回测配置。前往 **📊 回测** 标签页运行回测。")
                    else:
                        st.markdown(f'<div class="chat-container"><div class="chat-ai">🤖 {content}</div></div>', unsafe_allow_html=True)
        
        st.markdown("")
        
        # 快捷示例提示
        st.markdown("**💡 快捷示例：**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📈 稳健配置", use_container_width=True, key="quick1"):
                st.session_state["_quick_input"] = "帮我配一个稳健型组合：沪深300 40%、中证500 20%、国债ETF 20%、黄金ETF 20%"
        with col2:
            if st.button("🚀 激进成长", use_container_width=True, key="quick2"):
                st.session_state["_quick_input"] = "激进成长型：纳指100 50%、英伟达 20%、特斯拉 15%、黄金 15%"
        with col3:
            if st.button("🌍 全球均衡", use_container_width=True, key="quick3"):
                st.session_state["_quick_input"] = "全球均衡配置：标普500 30%、沪深300 30%、黄金 20%、长债 20%"
        
        # 输入框
        quick_val = st.session_state.pop("_quick_input", "")
        user_input = st.chat_input(
            "描述你想要的投资组合...",
            key="ai_chat_input",
        )
        
        # 如果点了快捷按钮，自动触发
        if quick_val and not user_input:
            user_input = quick_val
            st.session_state["_auto_send"] = quick_val
        
        if user_input:
            # 添加用户消息到历史
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            
            # 调用 AI
            with st.spinner("🤖 AI 正在分析..."):
                _cur_url, _cur_key, _cur_model = get_ai_config()
                result = parse_portfolio_with_ai(
                    user_input,
                    _cur_url,
                    _cur_key,
                    _cur_model,
                )
            
            if result:
                tickers = []
                weights = []
                display_data = []
                for item in result:
                    t = item.get("ticker", "")
                    w = item.get("weight", 0)
                    name = item.get("name", "")
                    tickers.append(t)
                    weights.append(w)
                    display_data.append({"资产": name, "Ticker": t, "权重": f"{w:.0%}"})
                
                # 自动填入配置
                st.session_state.tickers_str = ", ".join(tickers)
                st.session_state.weights_str = ", ".join([str(w) for w in weights])
                
                # 添加 AI 回复到历史
                st.session_state.chat_history.append({
                    "role": "ai",
                    "content": {
                        "message": f"已识别 {len(tickers)} 个资产，配置已自动填入！",
                        "config": display_data,
                    }
                })
            else:
                st.session_state.chat_history.append({
                    "role": "ai",
                    "content": "抱歉，我无法解析你的输入。请尝试更清晰地描述，例如：`60% 标普500 + 30% 黄金 + 10% 美债`"
                })
            
            st.rerun()
        
        # 清空聊天记录按钮
        if st.session_state.chat_history:
            st.markdown("")
            if st.button("🗑️ 清空聊天记录", key="clear_chat"):
                st.session_state.chat_history = []
                st.rerun()


# ============================================================
# Tab 2: 📊 回测
# ============================================================
with tab_backtest:
    # --- 输入区域（紧凑布局） ---
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
    
    # 常用资产速查（可折叠）
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

        # 获取设置（从 session state）
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
    
    # --- 显示结果（无论是刚运行还是之前运行过的） ---
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
        
        或者前往 **🤖 AI 对话** 标签页，用自然语言描述你的投资组合！
        """)


# ============================================================
# Tab 3: ⚙️ 设置
# ============================================================
with tab_settings:
    st.subheader("⚙️ 系统设置")
    
    # --- AI 配置 ---
    st.markdown('<div class="setting-card">', unsafe_allow_html=True)
    st.markdown("### 🤖 AI 配置")
    st.markdown("配置 OpenAI 兼容 API，用于自然语言解析资产配置。")
    
    col1, col2 = st.columns(2)
    with col1:
        ai_base_url = st.text_input(
            "Base URL",
            value=st.session_state.ai_base_url,
            help="OpenAI / DeepSeek / 通义千问等兼容 API 的地址",
            key="set_ai_base_url",
        )
        ai_api_key = st.text_input(
            "API Key",
            value=st.session_state.ai_api_key,
            type="password",
            help="你的 API Key",
            key="set_ai_api_key",
        )
    with col2:
        ai_model = st.text_input(
            "Model",
            value=st.session_state.ai_model,
            help="模型名称，如 gpt-4o-mini、deepseek-chat、qwen-turbo 等",
            key="set_ai_model",
        )
        st.markdown("")
        st.markdown("")
        if st.button("🔍 测试连接", key="test_ai_btn"):
            with st.spinner("正在测试 AI 连接..."):
                result = test_ai_connection(ai_base_url, ai_api_key, ai_model)
            if result["success"]:
                st.success(result["message"])
            else:
                st.error(result["message"])
    
    st.markdown('</div>', unsafe_allow_html=True)
    
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
        st.session_state.ai_base_url = ai_base_url
        st.session_state.ai_api_key = ai_api_key
        st.session_state.ai_model = ai_model
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