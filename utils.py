"""
投资组合回测工具函数模块 v2
=============================
- 数据源：AKShare（免费，覆盖 A股/港股/美股/ETF/加密货币）
- AI 解析：通用 OpenAI 兼容 API
- 图表：Plotly
"""

import os
import re
import json
import hashlib
import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


# ============================================================
# 预定义压力测试事件
# ============================================================
STRESS_EVENTS = {
    "2008-金融危机": {"start": "2007-10-09", "end": "2009-03-09", "desc": "次贷危机引发全球金融危机"},
    "2010-欧债危机": {"start": "2010-04-26", "end": "2010-07-02", "desc": "欧洲主权债务危机"},
    "2011-美债危机": {"start": "2011-07-22", "end": "2011-10-03", "desc": "美国债务上限危机"},
    "2015-A股股灾": {"start": "2015-06-12", "end": "2015-08-26", "desc": "中国A股市场大幅下跌"},
    "2018-贸易战": {"start": "2018-01-29", "end": "2018-12-24", "desc": "中美贸易摩擦升级"},
    "2020-COVID": {"start": "2020-02-20", "end": "2020-03-23", "desc": "新冠疫情引发全球市场暴跌"},
    "2020-反弹": {"start": "2020-03-23", "end": "2020-08-18", "desc": "疫情后市场快速反弹"},
    "2022-熊市": {"start": "2022-01-03", "end": "2022-10-12", "desc": "通胀飙升、加息周期引发熊市"},
    "2023-银行业危机": {"start": "2023-03-08", "end": "2023-03-24", "desc": "硅谷银行倒闭引发银行业恐慌"},
}


# ============================================================
# 常见资产名称 → Ticker 映射表（用于 AI 识别 fallback）
# ============================================================
ASSET_NAME_TO_TICKER = {
    # A 股指数
    "沪深300": "sh000300", "上证50": "sh000016", "中证500": "sh000905",
    "中证1000": "sh000852", "科创50": "sh000688", "创业板": "sz399006",
    # A 股 ETF
    "沪深300ETF": "sh510300", "创业板ETF": "sz159915", "科创50ETF": "sh588000",
    "中证500ETF": "sh510500", "上证50ETF": "sh510050", "纳指ETF": "sh513100",
    "标普500ETF": "sh513500", "黄金ETF": "sh518880", "国债ETF": "sh511010",
    "恒生ETF": "sh159920", "恒生科技ETF": "sh513180", "日经ETF": "sh513880",
    # 港股
    "腾讯": "00700", "阿里巴巴": "09988", "美团": "03690",
    "小米": "01810", "比亚迪": "01211", "京东": "09618",
    # 美股
    "苹果": "AAPL", "微软": "MSFT", "谷歌": "GOOGL", "亚马逊": "AMZN",
    "英伟达": "NVDA", "特斯拉": "TSLA", "Meta": "META", "台积电": "TSM",
    "标普500": "SPY", "纳指100": "QQQ", "道指": "DIA",
    "黄金": "GLD", "白银": "SLV", "长债": "TLT", "短债": "SHY",
    "石油": "USO", "天然气": "UNG", "新兴市场": "EEM", "亚太": "VWO",
}


# ============================================================
# Ticker 格式检测与转换
# ============================================================
def detect_market(ticker: str) -> str:
    """
    检测 ticker 所属市场，返回 "a_share" | "hk" | "us"
    """
    t = ticker.strip().upper()
    # 已有前缀的 A 股
    if t.startswith("SH") or t.startswith("SZ"):
        return "a_share"
    # 港股：5位纯数字
    if re.match(r'^\d{5}$', t):
        return "hk"
    # A 股：6位纯数字（如 000001）
    if re.match(r'^\d{6}$', t):
        return "a_share"
    # 其余默认为美股
    return "us"


def normalize_ticker_for_akshare(ticker: str) -> str:
    """
    将用户输入的 ticker 转换为 akshare 需要的格式。
    - A 股: sh000300 / sz000001
    - 港股: 00700
    - 美股: AAPL
    """
    t = ticker.strip()
    market = detect_market(t)

    if market == "a_share":
        t_upper = t.upper()
        if t_upper.startswith("SH") or t_upper.startswith("SZ"):
            return t_upper.lower()
        # 6位数字，判断沪深
        if t.startswith("6"):
            return f"sh{t}"
        else:
            return f"sz{t}"
    elif market == "hk":
        return t.zfill(5)
    else:
        return t.upper()


def normalize_display_name(ticker: str) -> str:
    """返回用于显示的标准化名称"""
    t = ticker.strip()
    market = detect_market(t)
    if market == "a_share":
        return t.upper() if t.upper().startswith(("SH", "SZ")) else (
            f"SH{t}" if t.startswith("6") else f"SZ{t}"
        )
    return t


# ============================================================
# AKShare 数据下载
# ============================================================
def _cache_path(ticker: str, start: str, end: str, data_dir: str = "data") -> Path:
    """生成缓存文件路径"""
    os.makedirs(data_dir, exist_ok=True)
    key = f"{ticker}_{start}_{end}"
    fname = hashlib.md5(key.encode()).hexdigest() + ".parquet"
    return Path(data_dir) / fname


def _download_a_share(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载 A 股数据（东方财富接口）"""
    import akshare as ak

    # 去掉 sh/sz 前缀，提取纯代码
    code = ticker.lower().replace("sh", "").replace("sz", "")
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")

    df = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start_fmt, end_date=end_fmt, adjust="qfq"
    )
    if df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"日期": "date", "收盘": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")[["close"]]
    return df


def _download_a_share_index(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载 A 股指数数据"""
    import akshare as ak

    code = ticker.lower().replace("sh", "").replace("sz", "")
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")

    df = ak.stock_zh_index_daily(symbol=ticker.lower())
    if df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"date": "date", "close": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)
    df = df.loc[start_dt:end_dt, ["close"]]
    return df


def _download_hk(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载港股数据"""
    import akshare as ak

    code = ticker.zfill(5)
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")

    df = ak.stock_hk_hist(symbol=code, period="daily",
                          start_date=start_fmt, end_date=end_fmt, adjust="qfq")
    if df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"日期": "date", "收盘": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")[["close"]]
    return df


def _download_us(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载美股数据"""
    import akshare as ak

    code = ticker.upper()
    df = ak.stock_us_daily(symbol=code, adjust="qfq")
    if df is None or df.empty:
        # 尝试带点号格式（如 BRK.B → BRK-B）
        code_alt = code.replace(".", "-")
        if code_alt != code:
            df = ak.stock_us_daily(symbol=code_alt, adjust="qfq")
        if df is None or df.empty:
            return pd.DataFrame()

    # 统一列名
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "close" in cl:
            col_map[c] = "close"
        elif "date" in cl:
            col_map[c] = "date"
    df = df.rename(columns=col_map)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    else:
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"

    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)
    df = df.loc[start_dt:end_dt, ["close"]]
    return df


def _download_single(ticker: str, start: str, end: str) -> pd.DataFrame:
    """根据市场类型选择下载方式"""
    market = detect_market(ticker)
    norm = normalize_ticker_for_akshare(ticker)

    try:
        if market == "a_share":
            code = norm.replace("sh", "").replace("sz", "")
            # 指数代码以 000/399 开头
            if code.startswith("000") or code.startswith("399"):
                return _download_a_share_index(norm, start, end)
            else:
                return _download_a_share(norm, start, end)
        elif market == "hk":
            return _download_hk(norm, start, end)
        else:
            return _download_us(norm, start, end)
    except Exception as e:
        print(f"下载 {ticker} 失败: {e}")
        return pd.DataFrame()


def download_data(
    tickers: List[str],
    start: str,
    end: str,
    data_dir: str = "data",
) -> Tuple[pd.DataFrame, List[str]]:
    """
    下载多只股票数据，优先读取本地缓存。
    返回: (prices DataFrame, invalid_tickers list)
    """
    prices = pd.DataFrame()
    invalid_tickers = []

    for ticker in tickers:
        cpath = _cache_path(ticker, start, end, data_dir)

        # 尝试读缓存
        if cpath.exists():
            try:
                df = pd.read_parquet(cpath)
                if not df.empty:
                    prices[ticker] = df["close"]
                    continue
            except Exception:
                pass

        # 下载
        df = _download_single(ticker, start, end)
        if df.empty:
            invalid_tickers.append(ticker)
            continue

        # 保存缓存
        df.to_parquet(cpath)
        prices[ticker] = df["close"]

    if not prices.empty:
        prices.index = pd.to_datetime(prices.index)
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(-1)
        prices = prices.sort_index()
        prices = prices.ffill().dropna(how="all")

    return prices, invalid_tickers


# ============================================================
# AI 自然语言解析资产配置
# ============================================================
ASSET_NAME_TO_TICKER = {
    # A 股指数
    "沪深300": "sh000300", "上证50": "sh000016", "中证500": "sh000905",
    "中证1000": "sh000852", "科创50": "sh000688", "创业板": "sz399006",
    # A 股 ETF
    "沪深300ETF": "sh510300", "创业板ETF": "sz159915", "科创50ETF": "sh588000",
    "中证500ETF": "sh510500", "上证50ETF": "sh510050", "纳指ETF": "sh513100",
    "标普500ETF": "sh513500", "黄金ETF": "sh518880", "国债ETF": "sh511010",
    "恒生ETF": "sh159920", "恒生科技ETF": "sh513180", "日经ETF": "sh513880",
    # 港股
    "腾讯": "00700", "阿里巴巴": "09988", "美团": "03690",
    "小米": "01810", "比亚迪": "01211", "京东": "09618",
    # 美股
    "苹果": "AAPL", "微软": "MSFT", "谷歌": "GOOGL", "亚马逊": "AMZN",
    "英伟达": "NVDA", "特斯拉": "TSLA", "Meta": "META", "台积电": "TSM",
    "标普500": "SPY", "纳指100": "QQQ", "道指": "DIA",
    "黄金": "GLD", "白银": "SLV", "长债": "TLT", "短债": "SHY",
    "石油": "USO", "天然气": "UNG", "新兴市场": "EEM", "亚太": "VWO",
}


def _build_asset_context() -> str:
    """构建资产映射上下文供 AI 参考"""
    lines = []
    for name, ticker in ASSET_NAME_TO_TICKER.items():
        lines.append(f"  {name}: {ticker}")
    return "\n".join(lines)


def test_ai_connection(base_url: str, api_key: str, model: str) -> dict:
    """
    测试 AI API 连通性。
    返回: {"success": bool, "message": str, "model": str}
    """
    try:
        from openai import OpenAI
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=10)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "说'连接成功'"}],
            max_tokens=20,
        )
        reply = response.choices[0].message.content.strip()
        actual_model = response.model if hasattr(response, 'model') else model
        return {"success": True, "message": f"连接成功！模型: {actual_model}", "model": actual_model}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}", "model": model}


def parse_portfolio_with_ai(
    user_input: str,
    base_url: str,
    api_key: str,
    model: str,
) -> Optional[List[Dict]]:
    """
    使用 AI 将自然语言解析为资产配置。
    
    返回: [{"ticker": "AAPL", "name": "苹果", "weight": 0.25}, ...] 或 None
    """
    try:
        from openai import OpenAI

        client = OpenAI(base_url=base_url, api_key=api_key)

        system_prompt = f"""你是一个专业的投资组合配置助手。用户会用自然语言描述他们想要的投资组合，你需要将其解析为结构化的 JSON 格式。

重要规则：
1. 必须输出合法的 JSON 数组
2. 每个元素包含 ticker、name、weight 三个字段
3. weight 是小数（如 0.25 表示 25%），所有 weight 之和应约等于 1
4. ticker 必须使用标准代码，参考以下映射表：

{_build_asset_context()}

如果用户提到的资产不在上述映射表中，请使用以下规则推断 ticker：
- A 股指数：sh000300（沪深300）、sh000016（上证50）等
- A 股个股：sz000001（平安银行）、sh600519（贵州茅台）等，沪市6开头用sh，深市用sz
- 港股：5位数字如 00700（腾讯）
- 美股：直接用代码如 AAPL、SPY

只输出 JSON，不要有其他任何文字。示例输出：
[{{"ticker": "SPY", "name": "标普500", "weight": 0.6}}, {{"ticker": "TLT", "name": "长债", "weight": 0.4}}]"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            temperature=0,
            max_tokens=2000,
        )

        content = response.choices[0].message.content.strip()
        # 提取 JSON 部分（可能被 ```json ``` 包裹）
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if isinstance(result, list) and len(result) > 0:
                return result

        return None

    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"AI 解析失败: {e}")
        return None


# ============================================================
# 组合收益计算（含再平衡）
# ============================================================
def calculate_portfolio_returns(
    prices: pd.DataFrame,
    weights: List[float],
    rebalance: str = "无",
) -> pd.Series:
    """计算加权组合收益率，支持再平衡。"""
    returns = prices.pct_change().dropna()
    weights_arr = np.array(weights)

    if rebalance == "无":
        portfolio_returns = returns.dot(weights_arr)
    else:
        freq = "M" if rebalance == "每月" else "Q"
        rebal_dates = returns.resample(freq).last().index

        port_val = pd.Series(1.0, index=returns.index)
        current_weights = weights_arr.copy()

        for i in range(1, len(returns)):
            date = returns.index[i]
            daily_ret = returns.iloc[i].values
            asset_values = current_weights * (1 + daily_ret)
            total_value = asset_values.sum()
            if total_value == 0:
                total_value = 1e-10
            current_weights = asset_values / total_value
            port_val.iloc[i] = port_val.iloc[i - 1] * total_value
            if date in rebal_dates:
                current_weights = weights_arr.copy()

        portfolio_returns = port_val.pct_change().dropna()

    return portfolio_returns


def calculate_benchmark_returns(prices: pd.Series) -> pd.Series:
    """计算基准日收益率"""
    return prices.pct_change().dropna()


# ============================================================
# 绩效指标计算
# ============================================================
def compute_metrics(returns: pd.Series, name: str = "组合") -> Dict[str, str]:
    """计算关键绩效指标"""
    if returns.empty or returns.isna().all():
        return {}

    total_days = len(returns)
    total_years = total_days / 252

    cumulative = (1 + returns).prod()
    total_return = cumulative - 1
    annual_return = (1 + total_return) ** (1 / max(total_years, 0.01)) - 1
    annual_vol = returns.std() * np.sqrt(252)

    rf = 0.02
    sharpe = (annual_return - rf) / annual_vol if annual_vol != 0 else 0

    downside = returns[returns < 0].std() * np.sqrt(252)
    sortino = (annual_return - rf) / downside if downside != 0 else 0

    cum_returns = (1 + returns).cumprod()
    running_max = cum_returns.cummax()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

    win_rate = (returns > 0).sum() / len(returns) if len(returns) > 0 else 0
    avg_win = returns[returns > 0].mean() if (returns > 0).any() else 0
    avg_loss = abs(returns[returns < 0].mean()) if (returns < 0).any() else 1e-10
    profit_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0

    dd_duration = 0
    max_dd_duration = 0
    for dd in drawdown:
        if dd < 0:
            dd_duration += 1
            max_dd_duration = max(max_dd_duration, dd_duration)
        else:
            dd_duration = 0

    return {
        "指标": name,
        "累计回报": f"{total_return:.2%}",
        "年化回报": f"{annual_return:.2%}",
        "年化波动率": f"{annual_vol:.2%}",
        "Sharpe": f"{sharpe:.3f}",
        "Sortino": f"{sortino:.3f}",
        "最大回撤": f"{max_drawdown:.2%}",
        "Calmar": f"{calmar:.3f}",
        "胜率": f"{win_rate:.2%}",
        "盈亏比": f"{profit_loss_ratio:.2f}",
        "最长回撤(天)": str(max_dd_duration),
        "交易天数": str(total_days),
    }


# ============================================================
# Plotly 图表
# ============================================================
def plot_equity_curve(
    portfolio_cum: pd.Series,
    benchmark_cum: Optional[pd.Series] = None,
    hedge_cum: Optional[pd.Series] = None,
    title: str = "权益曲线",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=portfolio_cum.index, y=portfolio_cum.values,
        mode="lines", name="组合", line=dict(color="#1f77b4", width=2),
    ))
    if benchmark_cum is not None:
        fig.add_trace(go.Scatter(
            x=benchmark_cum.index, y=benchmark_cum.values,
            mode="lines", name="基准", line=dict(color="#ff7f0e", width=2, dash="dash"),
        ))
    if hedge_cum is not None:
        fig.add_trace(go.Scatter(
            x=hedge_cum.index, y=hedge_cum.values,
            mode="lines", name="含对冲", line=dict(color="#2ca02c", width=2),
        ))
    fig.update_layout(
        title=title, xaxis_title="日期", yaxis_title="净值（起始=1）",
        template="plotly_white", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500,
    )
    return fig


def plot_drawdown(returns: pd.Series, benchmark_returns: Optional[pd.Series] = None) -> go.Figure:
    fig = go.Figure()
    cum = (1 + returns).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values, fill="tozeroy", name="组合回撤",
        line=dict(color="#d62728", width=1), fillcolor="rgba(214,39,40,0.3)",
    ))
    if benchmark_returns is not None and len(benchmark_returns) > 0:
        cum_b = (1 + benchmark_returns).cumprod()
        dd_b = (cum_b - cum_b.cummax()) / cum_b.cummax()
        fig.add_trace(go.Scatter(
            x=dd_b.index, y=dd_b.values, fill="tozeroy", name="基准回撤",
            line=dict(color="#ff7f0e", width=1), fillcolor="rgba(255,127,14,0.2)",
        ))
    fig.update_layout(
        title="回撤分析", xaxis_title="日期", yaxis_title="回撤",
        yaxis_tickformat=".0%", template="plotly_white", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=400,
    )
    return fig


def plot_monthly_heatmap(returns: pd.Series, title: str = "月度收益热力图") -> go.Figure:
    monthly = returns.resample("M").apply(lambda x: (1 + x).prod() - 1)
    monthly_df = pd.DataFrame({
        "year": monthly.index.year, "month": monthly.index.month, "return": monthly.values,
    })
    pivot = monthly_df.pivot(index="year", columns="month", values="return")
    pivot.columns = [f"{m}月" for m in pivot.columns]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale="RdYlGn", zmid=0,
        text=np.round(pivot.values * 100, 1), texttemplate="%{text:.1f}%",
        hovertemplate="年份: %{y}<br>月份: %{x}<br>收益: %{z:.2%}<extra></extra>",
    ))
    fig.update_layout(title=title, template="plotly_white",
                      height=max(300, len(pivot) * 35 + 100))
    return fig


def plot_annual_returns(returns: pd.Series, benchmark_returns: Optional[pd.Series] = None) -> go.Figure:
    annual = returns.resample("Y").apply(lambda x: (1 + x).prod() - 1)
    annual.index = annual.index.year

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=annual.index.astype(str), y=annual.values, name="组合",
        marker_color="#1f77b4",
        text=[f"{v:.1%}" for v in annual.values], textposition="outside",
    ))
    if benchmark_returns is not None and len(benchmark_returns) > 0:
        annual_b = benchmark_returns.resample("Y").apply(lambda x: (1 + x).prod() - 1)
        annual_b.index = annual_b.index.year
        common_idx = annual.index.intersection(annual_b.index)
        if len(common_idx) > 0:
            fig.add_trace(go.Bar(
                x=common_idx.astype(str), y=annual_b.loc[common_idx].values,
                name="基准", marker_color="#ff7f0e",
                text=[f"{v:.1%}" for v in annual_b.loc[common_idx].values],
                textposition="outside",
            ))
    fig.update_layout(title="年度收益对比", yaxis_tickformat=".0%",
                      template="plotly_white", barmode="group", height=400)
    return fig


# ============================================================
# 压力测试
# ============================================================
def stress_test(
    portfolio_returns: pd.Series,
    benchmark_returns: Optional[pd.Series],
    events: Dict[str, Dict],
) -> pd.DataFrame:
    results = []
    for event_name, info in events.items():
        start = pd.Timestamp(info["start"])
        end = pd.Timestamp(info["end"])
        mask = (portfolio_returns.index >= start) & (portfolio_returns.index <= end)
        period_returns = portfolio_returns[mask]
        if period_returns.empty:
            continue

        total_ret = (1 + period_returns).prod() - 1
        cum = (1 + period_returns).cumprod()
        max_dd = ((cum - cum.cummax()) / cum.cummax()).min()

        row = {
            "事件": event_name, "时间范围": f"{info['start']} ~ {info['end']}",
            "描述": info.get("desc", ""), "组合回报": f"{total_ret:.2%}",
            "组合最大回撤": f"{max_dd:.2%}", "交易天数": len(period_returns),
        }

        if benchmark_returns is not None:
            mask_b = (benchmark_returns.index >= start) & (benchmark_returns.index <= end)
            period_bench = benchmark_returns[mask_b]
            if not period_bench.empty:
                bench_ret = (1 + period_bench).prod() - 1
                cum_b = (1 + period_bench).cumprod()
                bench_dd = ((cum_b - cum_b.cummax()) / cum_b.cummax()).min()
                row["基准回报"] = f"{bench_ret:.2%}"
                row["基准最大回撤"] = f"{bench_dd:.2%}"
                row["超额回报"] = f"{total_ret - bench_ret:.2%}"

        results.append(row)
    return pd.DataFrame(results)


def plot_stress_test(stress_df: pd.DataFrame) -> go.Figure:
    if stress_df.empty:
        fig = go.Figure()
        fig.update_layout(title="压力测试（无可用数据）")
        return fig

    port_ret = stress_df["组合回报"].str.rstrip("%").astype(float) / 100
    port_dd = stress_df["组合最大回撤"].str.rstrip("%").astype(float) / 100

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=("各事件下组合回报", "各事件下最大回撤"),
                        horizontal_spacing=0.15)

    fig.add_trace(go.Bar(
        x=stress_df["事件"], y=port_ret, name="组合回报",
        marker_color="#1f77b4", text=[f"{v:.1%}" for v in port_ret], textposition="outside",
    ), row=1, col=1)

    if "基准回报" in stress_df.columns:
        bench_ret = stress_df["基准回报"].str.rstrip("%").astype(float) / 100
        fig.add_trace(go.Bar(
            x=stress_df["事件"], y=bench_ret, name="基准回报",
            marker_color="#ff7f0e", text=[f"{v:.1%}" for v in bench_ret], textposition="outside",
        ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=stress_df["事件"], y=port_dd, name="组合回撤",
        marker_color="#d62728", text=[f"{v:.1%}" for v in port_dd], textposition="outside",
    ), row=1, col=2)

    if "基准最大回撤" in stress_df.columns:
        bench_dd = stress_df["基准最大回撤"].str.rstrip("%").astype(float) / 100
        fig.add_trace(go.Bar(
            x=stress_df["事件"], y=bench_dd, name="基准回撤",
            marker_color="#ffbb33", text=[f"{v:.1%}" for v in bench_dd], textposition="outside",
        ), row=1, col=2)

    fig.update_layout(
        template="plotly_white", barmode="group", height=450,
        yaxis_tickformat=".0%", yaxis2_tickformat=".0%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# ============================================================
# 对冲效果对比
# ============================================================
def calculate_hedge_portfolio(
    prices: pd.DataFrame,
    weights: List[float],
    hedge_ticker: str,
    hedge_weight: float,
    rebalance: str = "无",
) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    original_returns = calculate_portfolio_returns(prices, weights, rebalance)

    start = prices.index[0].strftime("%Y-%m-%d")
    end = prices.index[-1].strftime("%Y-%m-%d")
    hedge_prices, invalid = download_data([hedge_ticker], start, end)
    if hedge_ticker in invalid or hedge_prices.empty:
        return original_returns, None

    all_prices = prices.copy()
    hedge_col = hedge_prices.columns[0]
    all_prices[hedge_ticker] = hedge_prices[hedge_col]
    all_prices = all_prices.dropna()

    if all_prices.empty:
        return original_returns, None

    main_weight = 1 - hedge_weight
    new_weights = [w * main_weight for w in weights] + [hedge_weight]
    hedge_returns = calculate_portfolio_returns(all_prices, new_weights, rebalance)
    return original_returns, hedge_returns


# ============================================================
# HTML 报告生成
# ============================================================
def generate_html_report(
    metrics_df, portfolio_cum, benchmark_cum, hedge_cum,
    drawdown_returns, benchmark_drawdown_returns,
    monthly_returns, stress_df, config_info,
) -> str:
    report_date = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    eq_fig = plot_equity_curve(portfolio_cum, benchmark_cum, hedge_cum, "权益曲线")
    dd_fig = plot_drawdown(drawdown_returns, benchmark_drawdown_returns)
    hm_fig = plot_monthly_heatmap(monthly_returns)
    ar_fig = plot_annual_returns(monthly_returns, benchmark_drawdown_returns)

    eq_html = eq_fig.to_html(full_html=False, include_plotlyjs="cdn")
    dd_html = dd_fig.to_html(full_html=False, include_plotlyjs=False)
    hm_html = hm_fig.to_html(full_html=False, include_plotlyjs=False)
    ar_html = ar_fig.to_html(full_html=False, include_plotlyjs=False)

    metrics_html = metrics_df.to_html(index=False, classes="metrics-table") if not metrics_df.empty else "<p>无数据</p>"

    stress_html = ""
    if not stress_df.empty:
        stress_html = stress_df.to_html(index=False, classes="metrics-table")
        stress_chart = plot_stress_test(stress_df)
        stress_html += stress_chart.to_html(full_html=False, include_plotlyjs=False)

    config_html = f"""
    <ul>
        <li><strong>Tickers:</strong> {config_info.get('tickers', '')}</li>
        <li><strong>权重:</strong> {config_info.get('weights', '')}</li>
        <li><strong>回测起始:</strong> {config_info.get('start', '')}</li>
        <li><strong>再平衡:</strong> {config_info.get('rebalance', '无')}</li>
        <li><strong>基准:</strong> {config_info.get('benchmark', 'N/A')}</li>
    </ul>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8"><title>投资组合回测报告</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        h1 {{ color: #1f77b4; border-bottom: 3px solid #1f77b4; padding-bottom: 10px; }}
        h2 {{ color: #333; margin-top: 30px; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .metrics-table {{ width: 100%; border-collapse: collapse; }}
        .metrics-table th, .metrics-table td {{ border: 1px solid #ddd; padding: 10px; text-align: center; }}
        .metrics-table th {{ background: #1f77b4; color: white; }}
        .metrics-table tr:nth-child(even) {{ background: #f9f9f9; }}
        .footer {{ text-align: center; color: #999; margin-top: 30px; padding: 20px; }}
    </style>
</head>
<body>
    <h1>📊 投资组合回测报告</h1>
    <p>生成时间: {report_date}</p>
    <div class="card"><h2>📋 回测配置</h2>{config_html}</div>
    <div class="card"><h2>📈 绩效指标</h2>{metrics_html}</div>
    <div class="card"><h2>💹 权益曲线</h2>{eq_html}</div>
    <div class="card"><h2>📉 回撤分析</h2>{dd_html}</div>
    <div class="card"><h2>📊 年度收益</h2>{ar_html}</div>
    <div class="card"><h2>🗓️ 月度收益热力图</h2>{hm_html}</div>
    <div class="card"><h2>⚡ 压力测试</h2>{stress_html}</div>
    <div class="footer"><p>由 Streamlit Backtest App 自动生成</p></div>
</body></html>"""