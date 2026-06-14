"""
投资组合回测工具函数模块
========================
- 数据源：AKShare（免费，覆盖 A股/港股/美股/ETF/加密货币）
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
# 资产分类数据库（按市场 → 类型两级分类，160+ 全球资产）
# ============================================================
ASSET_CATALOG = {
    "🇨🇳 A股": {
        "指数": {
            "沪深300": "sh000300",
            "上证50": "sh000016",
            "中证500": "sh000905",
            "中证1000": "sh000852",
            "科创50": "sh000688",
            "创业板指": "sz399006",
            "中证全指": "sh000985",
            "中证红利": "sh000922",
            "国证芯片": "sz399986",
            "中证消费": "sh000932",
            "中证医药": "sh000933",
            "中证银行": "sh399986",
        },
        "ETF-宽基": {
            "沪深300ETF": "sh510300",
            "创业板ETF": "sz159915",
            "科创50ETF": "sh588000",
            "中证500ETF": "sh510500",
            "上证50ETF": "sh510050",
            "中证1000ETF": "sz159845",
            "A50ETF": "sh159593",
            "MSCI中国A50ETF": "sh560050",
            "中证A500ETF": "sh159338",
        },
        "ETF-跨境": {
            "纳指ETF": "sh513100",
            "标普500ETF": "sh513500",
            "恒生ETF": "sh159920",
            "恒生科技ETF": "sh513180",
            "日经ETF": "sh513880",
            "德国ETF": "sh513030",
            "法国ETF": "sh513580",
            "英国ETF": "sh513520",
            "越南ETF": "sz159822",
            "印度基金LOF": "sh164824",
        },
        "ETF-商品": {
            "黄金ETF": "sh518880",
            "白银ETF": "sz161226",
            "豆粕ETF": "sz159985",
            "石油ETF": "sz159697",
            "有色金属ETF": "sh512400",
            "能源化工ETF": "sh159981",
        },
        "ETF-债券": {
            "国债ETF": "sh511010",
            "信用债ETF": "sh511220",
            "十年国债ETF": "sh511260",
            "可转债ETF": "sh511380",
        },
        "ETF-行业": {
            "券商ETF": "sh512000",
            "医药ETF": "sh512010",
            "芯片ETF": "sz159995",
            "新能源ETF": "sh561610",
            "军工ETF": "sh512660",
            "银行ETF": "sh512800",
            "地产ETF": "sh512200",
            "消费ETF": "sh159928",
            "科技ETF": "sh515000",
            "人工智能ETF": "sh515070",
            "机器人ETF": "sz562500",
            "游戏ETF": "sz159869",
            "碳中和ETF": "sz159790",
            "传媒ETF": "sh512980",
            "养殖ETF": "sz159865",
            "酒ETF": "sh512690",
            "汽车ETF": "sz159768",
            "光伏ETF": "sh515790",
            "稀土ETF": "sh516150",
            "基建ETF": "sh516950",
        },
        "个股": {
            "贵州茅台": "600519",
            "宁德时代": "300750",
            "比亚迪": "002594",
            "招商银行": "600036",
            "中国平安": "601318",
            "隆基绿能": "601012",
            "五粮液": "000858",
            "美的集团": "000333",
            "中信证券": "600030",
            "恒瑞医药": "600276",
            "海天味业": "603288",
            "三一重工": "600031",
        },
    },
    "🇭🇰 港股": {
        "指数": {
            "恒生指数": "HSI",
            "恒生科技指数": "HSTECH",
            "国企指数": "HSCEI",
        },
        "个股": {
            "腾讯控股": "00700",
            "阿里巴巴-W": "09988",
            "美团-W": "03690",
            "小米集团-W": "01810",
            "比亚迪H": "01211",
            "京东集团-SW": "09618",
            "网易-S": "09999",
            "快手-W": "01024",
            "中芯国际": "00981",
            "中国移动": "00941",
            "建设银行H": "00939",
            "工商银行H": "01398",
            "中国平安H": "02318",
        },
    },
    "🇺🇸 美股": {
        "指数": {
            "标普500 (SPY)": "SPY",
            "纳指100 (QQQ)": "QQQ",
            "道琼斯 (DIA)": "DIA",
            "罗素2000 (IWM)": "IWM",
            "VIX恐慌指数": "VIX",
        },
        "科技巨头": {
            "苹果 Apple": "AAPL",
            "微软 Microsoft": "MSFT",
            "谷歌-A Alphabet": "GOOGL",
            "亚马逊 Amazon": "AMZN",
            "英伟达 NVIDIA": "NVDA",
            "特斯拉 Tesla": "TSLA",
            "Meta Platforms": "META",
            "台积电 TSMC": "TSM",
            "博通 Broadcom": "AVGO",
            "高通 Qualcomm": "QCOM",
            "AMD": "AMD",
            "超微电脑 SMCI": "SMCI",
            "奈飞 Netflix": "NFLX",
        },
        "金融医药": {
            "伯克希尔B Berkshire": "BRK-B",
            "摩根大通 JPMorgan": "JPM",
            "高盛 Goldman Sachs": "GS",
            "联合健康 UnitedHealth": "UNH",
            "强生 Johnson&Johnson": "JNJ",
            "辉瑞 Pfizer": "PFE",
            "礼来 Eli Lilly": "LLY",
        },
        "消费工业": {
            "沃尔玛 Walmart": "WMT",
            "可口可乐 Coca-Cola": "KO",
            "宝洁 P&G": "PG",
            "麦当劳 McDonald's": "MCD",
            "耐克 Nike": "NKE",
            "迪士尼 Disney": "DIS",
            "波音 Boeing": "BA",
            "卡特彼勒 Caterpillar": "CAT",
        },
        "ETF-宽基": {
            "标普500ETF-先锋 VOO": "VOO",
            "标普500ETF-iShares IVV": "IVV",
            "纳指100-3倍做多 TQQQ": "TQQQ",
            "纳指100-3倍做空 SQQQ": "SQQQ",
            "ARK创新ETF ARKK": "ARKK",
        },
        "ETF-行业": {
            "科技ETF (XLK)": "XLK",
            "金融ETF (XLF)": "XLF",
            "能源ETF (XLE)": "XLE",
            "医疗ETF (XLV)": "XLV",
            "工业ETF (XLI)": "XLI",
            "消费ETF (XLY)": "XLY",
            "公用事业ETF (XLU)": "XLU",
            "房地产ETF (XLRE)": "XLRE",
            "半导体ETF (SOXX)": "SOXX",
            "AI机器人ETF (BOTZ)": "BOTZ",
            "清洁能源ETF (ICLN)": "ICLN",
        },
        "ETF-商品": {
            "黄金ETF (GLD)": "GLD",
            "白银ETF (SLV)": "SLV",
            "黄金矿业ETF (GDX)": "GDX",
            "石油ETF (USO)": "USO",
            "天然气ETF (UNG)": "UNG",
            "农产品ETF (DBA)": "DBA",
            "铜矿ETF (COPX)": "COPX",
            "宽基商品ETF (DJP)": "DJP",
        },
        "ETF-债券": {
            "长期国债ETF (TLT)": "TLT",
            "中期国债ETF (IEF)": "IEF",
            "短期国债ETF (SHY)": "SHY",
            "投资级债ETF (LQD)": "LQD",
            "高收益债ETF (HYG)": "HYG",
            "TIPS通胀保护 (TIP)": "TIP",
        },
        "ETF-另类": {
            "新兴市场ETF (EEM)": "EEM",
            "新兴市场ETF-先锋 (VWO)": "VWO",
            "VIX短仓ETF (VIXY)": "VIXY",
            "杠杆VIX (UVXY)": "UVXY",
            "前沿市场ETF (FM)": "FM",
        },
    },
    "🇯🇵 日本": {
        "指数": {
            "日经225": "^N225",
            "东证指数": "1306.T",
        },
        "ETF": {
            "日经ETF(国内)": "sh513880",
            "MAXIS日经225ETF": "1330.T",
        },
    },
    "🇪🇺 欧洲": {
        "指数": {
            "德国DAX": "^GDAXI",
            "英国富时100": "^FTSE",
            "法国CAC40": "^FCHI",
            "欧洲斯托克50": "^STOXX50E",
        },
        "ETF(国内)": {
            "德国ETF": "sh513030",
            "法国ETF": "sh513580",
            "英国ETF": "sh513520",
        },
    },
    "🌏 其他市场": {
        "指数": {
            "印度Nifty50": "^NSEI",
            "巴西BOVESPA": "^BVSP",
            "澳洲ASX200": "^AXJO",
            "韩国KOSPI": "^KS11",
            "台湾加权": "^TWII",
        },
    },
    "₿ 加密货币": {
        "主流币": {
            "比特币 Bitcoin": "BTC-USD",
            "以太坊 Ethereum": "ETH-USD",
            "Solana": "SOL-USD",
            "BNB": "BNB-USD",
            "瑞波币 XRP": "XRP-USD",
            "莱特币 Litecoin": "LTC-USD",
        },
    },
    "💱 外汇": {
        "主要货币对": {
            "欧元/美元 EUR/USD": "EURUSD=X",
            "美元/日元 USD/JPY": "JPY=X",
            "英镑/美元 GBP/USD": "GBPUSD=X",
            "美元/人民币 USD/CNY": "CNY=X",
            "美元指数 DXY": "DX-Y.NYB",
            "澳元/美元 AUD/USD": "AUDUSD=X",
        },
    },
    "🛢️ 大宗商品": {
        "期货": {
            "WTI原油": "CL=F",
            "布伦特原油": "BZ=F",
            "黄金期货": "GC=F",
            "白银期货": "SI=F",
            "铜期货": "HG=F",
            "天然气期货": "NG=F",
        },
    },
}


def get_flat_asset_map() -> dict:
    """将 ASSET_CATALOG 展平为 {显示标签: ticker} 映射表"""
    flat = {}
    for market, types in ASSET_CATALOG.items():
        for asset_type, assets in types.items():
            for name, ticker in assets.items():
                label = f"{market} · {asset_type} | {name} ({ticker})"
                flat[label] = ticker
    return flat


ASSET_LABEL_TO_TICKER = get_flat_asset_map()
ASSET_NAME_TO_TICKER = {}  # 向后兼容：展平的 {中文名: ticker}


def _build_name_to_ticker():
    """构建简单的名称到ticker映射（向后兼容）"""
    flat = {}
    for _market, types in ASSET_CATALOG.items():
        for _type, assets in types.items():
            flat.update(assets)
    return flat


ASSET_NAME_TO_TICKER = _build_name_to_ticker()


def get_asset_options() -> list:
    """获取所有资产的显示标签列表（用于 selectbox），格式：'市场 · 类型 | 名称 (代码)'"""
    return sorted(ASSET_LABEL_TO_TICKER.keys())


def search_assets(keyword: str) -> list:
    """
    在 ASSET_CATALOG 中模糊搜索资产名称/代码，返回匹配列表。
    每项为 dict: {"market", "type", "name", "ticker", "label"}
    """
    results = []
    keyword = keyword.strip().lower()
    if not keyword:
        return results
    for market, types in ASSET_CATALOG.items():
        for asset_type, assets in types.items():
            for name, ticker in assets.items():
                if (keyword in name.lower() or
                    keyword in ticker.lower() or
                        keyword in market.lower()):
                    label = f"{market} · {asset_type} | {name} ({ticker})"
                    results.append({
                        "market": market,
                        "type": asset_type,
                        "name": name,
                        "ticker": ticker,
                        "label": label,
                    })
    return results


def get_assets_by_market(market: str) -> dict:
    """获取指定市场下的所有资产，返回 {type: {name: ticker}}"""
    return ASSET_CATALOG.get(market, {})


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


def _download_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    使用 yfinance 下载数据（通用回退方案）
    支持全球所有市场：美股、欧洲指数、港股、加密货币等
    """
    import yfinance as yf

    # 将带 HK 后缀的格式转换为 yfinance 格式
    yf_ticker = ticker.strip()
    # 尝试下载
    df = yf.download(yf_ticker, start=start, end=end, progress=False, auto_adjust=True)

    if df is None or df.empty:
        return pd.DataFrame()

    # 处理 MultiIndex columns（yfinance 有时返回多级列）
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 找到 Close 列
    close_col = None
    for c in df.columns:
        if c.lower() == "close":
            close_col = c
            break
    if close_col is None:
        return pd.DataFrame()

    result = df[[close_col]].copy()
    result.columns = ["close"]
    result.index = pd.to_datetime(result.index)
    result.index.name = "date"
    return result


def _download_single(ticker: str, start: str, end: str, retries: int = 2) -> pd.DataFrame:
    """
    根据市场类型选择下载方式，支持自动重试。
    优先使用 akshare（A股/港股/美股），失败时回退到 yfinance（支持全球市场）。
    每次重试间隔递增（1秒、2秒），避免限流。
    """
    import time as _time

    market = detect_market(ticker)
    norm = normalize_ticker_for_akshare(ticker)

    for attempt in range(retries + 1):
        # 第一步：尝试 akshare
        try:
            if market == "a_share":
                code = norm.replace("sh", "").replace("sz", "")
                if code.startswith("000") or code.startswith("399"):
                    # 指数数据：尝试多个接口
                    try:
                        df = _download_a_share_index(norm, start, end)
                    except Exception:
                        import akshare as ak
                        code = norm.lower().replace("sh", "").replace("sz", "")
                        df = ak.index_zh_a_hist(
                            symbol=code, period="daily",
                            start_date=start.replace("-", ""),
                            end_date=end.replace("-", ""),
                        )
                        if df is not None and not df.empty:
                            col_map = {}
                            for c in df.columns:
                                cl = c.lower()
                                if "close" in cl or "收盘" in cl:
                                    col_map[c] = "close"
                                elif "date" in cl or "日期" in cl:
                                    col_map[c] = "date"
                            df = df.rename(columns=col_map)
                            if "date" in df.columns:
                                df["date"] = pd.to_datetime(df["date"])
                                df = df.set_index("date")
                            df = df[["close"]]
                else:
                    df = _download_a_share(norm, start, end)
            elif market == "hk":
                df = _download_hk(norm, start, end)
            else:
                df = _download_us(norm, start, end)

            if df is not None and not df.empty:
                return df
        except Exception as e:
            err_msg = str(e)
            if attempt < retries:
                _time.sleep(1 + attempt)  # 递增等待
                continue
            print(f"akshare 下载 {ticker} 失败（{retries+1}次尝试）: {err_msg}")

        # 第二步：yfinance 回退（支持欧洲指数、港股.HK后缀等）
        try:
            # A股需要转换格式给 yfinance
            yf_ticker = ticker
            if market == "a_share":
                code = norm.lower().replace("sh", "").replace("sz", "")
                if code.startswith("6"):
                    yf_ticker = f"{code}.SS"
                else:
                    yf_ticker = f"{code}.SZ"

            df = _download_yfinance(yf_ticker, start, end)
            if df is not None and not df.empty:
                print(f"✓ yfinance 成功下载 {ticker}（akshare 失败后回退）")
                return df
        except Exception as e:
            if attempt < retries:
                _time.sleep(1 + attempt)
                continue
            print(f"yfinance 下载 {ticker} 也失败: {e}")

        if attempt < retries:
            _time.sleep(1 + attempt)

    return pd.DataFrame()


def download_data(
    tickers: list, start: str, end: str
) -> tuple:
    """
    批量下载多个 ticker 的收盘价数据。
    返回 (prices_df, invalid_tickers, error_details)
    - prices_df: DataFrame, index=日期, columns=ticker, values=收盘价
    - invalid_tickers: 下载失败的 ticker 列表
    - error_details: {ticker: error_msg} 详细的错误信息
    """
    import time

    prices_dict = {}
    invalid_tickers = []
    error_details = {}

    for i, ticker in enumerate(tickers):
        try:
            df = _download_single(ticker, start, end)
            if df is None or df.empty:
                invalid_tickers.append(ticker)
                error_details[ticker] = "下载成功但返回空数据，请检查 ticker 是否正确"
                continue
            if len(df) < 5:
                invalid_tickers.append(ticker)
                error_details[ticker] = f"数据不足（仅 {len(df)} 条记录），可能 ticker 有误或日期范围太短"
                continue
            prices_dict[ticker] = df["close"]
        except Exception as e:
            err_msg = str(e)[:200]  # 截断过长的错误信息
            print(f"⚠️ 下载 {ticker} 失败: {err_msg}")
            invalid_tickers.append(ticker)
            error_details[ticker] = err_msg
        time.sleep(0.3)  # 限速，避免触发数据源封禁

    if prices_dict:
        prices_df = pd.DataFrame(prices_dict)
        prices_df = prices_df.dropna(how="all")
        # 对齐所有资产到相同日期范围（取交集）
        if len(prices_dict) > 1:
            prices_df = prices_df.dropna()  # 只保留所有资产都有数据的日期
    else:
        prices_df = pd.DataFrame()

    return prices_df, invalid_tickers


# ============================================================
# 组合收益计算（含再平衡）
# ============================================================
def calculate_portfolio_returns(
    prices: pd.DataFrame, weights: List[float], rebalance: str = "无"
) -> pd.Series:
    """
    计算组合日收益率（含再平衡）
    """
    daily_returns = prices.pct_change().dropna()
    weights_arr = np.array(weights)

    if rebalance == "无":
        # 买入持有：计算加权收益
        port_returns = (daily_returns * weights_arr).sum(axis=1)
    elif rebalance == "每月":
        port_returns = _rebalanced_returns(daily_returns, weights_arr, "M")
    elif rebalance == "每季度":
        port_returns = _rebalanced_returns(daily_returns, weights_arr, "Q")
    else:
        port_returns = (daily_returns * weights_arr).sum(axis=1)

    return port_returns


def _rebalanced_returns(
    daily_returns: pd.DataFrame, weights: np.ndarray, freq: str
) -> pd.Series:
    """按指定频率再平衡"""
    port_value = 1.0
    values = []
    current_weights = weights.copy()
    rebalance_dates = set(daily_returns.resample(freq).last().index)

    for date in daily_returns.index:
        day_returns = daily_returns.loc[date].values
        current_weights = current_weights * (1 + day_returns)
        total = current_weights.sum()
        if total > 0:
            current_weights = current_weights / total
        port_value *= 1 + np.dot(weights, day_returns)
        values.append(port_value)

        if date in rebalance_dates:
            current_weights = weights.copy()

    result = pd.Series(values[1:], index=daily_returns.index[1:])
    return result.pct_change().dropna()


def calculate_benchmark_portfolio_returns(
    prices: pd.DataFrame, weights: List[float]
) -> pd.Series:
    """
    计算基准组合（多资产加权）的日收益率。
    不支持再平衡，使用买入持有策略。
    """
    daily_returns = prices.pct_change().dropna()
    weights_arr = np.array(weights)
    port_returns = (daily_returns * weights_arr).sum(axis=1)
    return port_returns


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