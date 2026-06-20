"""
投资组合回测工具函数模块
========================
- 数据源：新浪财经 + AKShare + yfinance + FMP（多源瀑布式回退）
- 回测引擎：纯 pandas/numpy（无 vectorbt 依赖）
- 图表：Plotly
"""

import os
import re
import datetime as dt
import json
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================
# 代理绕过工具（线程安全版本）
# ============================================================
_PROXY_LOCK = threading.Lock()


def _bypass_proxy(func, *args, **kwargs):
    """在无代理环境下执行函数（线程安全）
    
    清除所有代理环境变量（大小写变体），确保 requests / urllib 
    不会读取 macOS Keychain 系统代理或环境变量代理。
    """
    with _PROXY_LOCK:
        old_env = {}
        # 清除所有可能的代理变量（大小写变体）
        proxy_keys = (
            "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
            "ALL_PROXY", "all_proxy", "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
        )
        for k in proxy_keys:
            if k in os.environ:
                old_env[k] = os.environ.pop(k)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        try:
            return func(*args, **kwargs)
        finally:
            for k in proxy_keys:
                os.environ.pop(k, None)
            os.environ.update(old_env)


def _no_proxy_session():
    """创建一个绕过系统代理的 requests.Session
    
    关键: trust_env=False 让 requests 不读取 macOS Keychain 系统代理
    """
    import requests
    s = requests.Session()
    s.trust_env = False  # 不读取系统代理设置
    return s


def _clean_prices_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    统一清洗 prices DataFrame，确保：
    1. 列名是扁平字符串（非 MultiIndex/元组）
    2. 列名唯一（无重复）
    3. 所有数据是数值类型
    4. index 是 DatetimeIndex
    """
    if df.empty:
        return df

    # 扁平化 MultiIndex 列
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]) if isinstance(c, tuple) else str(c) for c in df.columns]

    # 确保列名是字符串
    df.columns = [str(c) for c in df.columns]

    # 去除重复列名（保留第一列）
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    # 确保所有数据是数值类型
    df = df.copy()
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 确保 index 是 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df


# ============================================================
# FMP（Financial Modeling Prep）免费 API 配置
# ============================================================
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


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
# 资产分类数据库（按市场 -> 类型两级分类，160+ 全球资产）
# ============================================================
ASSET_CATALOG = {
    "\U0001f1e8\U0001f1f3 A股": {
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
            "中证银行": "sh000997",
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
            "半导体ETF": "sh512480",
            "新能源ETF": "sh516160",
            "消费ETF": "sh159928",
            "医药ETF": "sh512010",
            "银行ETF": "sh512800",
            "军工ETF": "sh512660",
            "证券ETF": "sh512880",
            "白酒ETF": "sz161725",
            "光伏ETF": "sz159857",
            "碳中和ETF": "sh516070",
            "人工智能ETF": "sh515070",
            "机器人ETF": "sz159770",
        },
    },
    "\U0001f1ed\U0001f1f0 港股": {
        "个股": {
            "腾讯控股": "00700",
            "阿里巴巴-SW": "09988",
            "美团-W": "03690",
            "小米集团-W": "01810",
            "建设银行": "00939",
            "中国移动": "00941",
            "友邦保险": "01299",
            "比亚迪股份": "01211",
        },
        "指数": {
            "恒生指数": "HSI",
            "恒生科技": "HSTECH",
            "恒生国企": "HSCEI",
        },
    },
    "\U0001f1fa\U0001f1f8 美股": {
        "大盘股": {
            "苹果": "AAPL",
            "微软": "MSFT",
            "谷歌A": "GOOGL",
            "亚马逊": "AMZN",
            "英伟达": "NVDA",
            "特斯拉": "TSLA",
            "Meta": "META",
            "伯克希尔B": "BRK-B",
            "台积电": "TSM",
            "博通": "AVGO",
        },
        "ETF-大盘": {
            "标普500ETF": "SPY",
            "纳指100ETF": "QQQ",
            "道指ETF": "DIA",
            "罗素2000ETF": "IWM",
            "标普等权ETF": "RSP",
        },
        "ETF-行业": {
            "半导体ETF": "SMH",
            "生物科技ETF": "IBB",
            "清洁能源ETF": "ICLN",
            "网络安全ETF": "CIBR",
            "云计算ETF": "SKYY",
            "AI ETF": "AIQ",
            "军工ETF": "ITA",
            "高股利ETF": "VYM",
        },
        "ETF-债券": {
            "美国国债20Y": "TLT",
            "投资级公司债": "LQD",
            "高收益债": "HYG",
            "TIPs通胀保护": "TIP",
            "短期国债": "SHY",
        },
        "ETF-波动率": {
            "VIX短期期货": "VXX",
        },
    },
    "\U0001f30d 全球指数": {
        "主要指数": {
            "标普500": "^GSPC",
            "纳斯达克": "^IXIC",
            "道琼斯": "^DJI",
            "日经225": "^N225",
            "德国DAX": "^GDAXI",
            "英国富时100": "^FTSE",
            "法国CAC40": "^FCHI",
            "韩国KOSPI": "^KS11",
            "印度Nifty50": "^NSEI",
        },
    },
    "\U0001f4b0 商品": {
        "贵金属": {
            "黄金期货": "GC=F",
            "白银期货": "SI=F",
            "铂金期货": "PL=F",
        },
        "能源": {
            "原油期货WTI": "CL=F",
            "天然气期货": "NG=F",
            "布伦特原油": "BZ=F",
        },
        "农产品": {
            "玉米期货": "ZC=F",
            "小麦期货": "ZW=F",
            "大豆期货": "ZS=F",
        },
        "工业金属": {
            "铜期货": "HG=F",
        },
        "ETF-商品": {
            "黄金ETF": "GLD",
            "白银ETF": "SLV",
            "石油ETF": "USO",
            "天然气ETF": "UNG",
            "农产品DBA": "DBA",
        },
    },
    "\U0001f4b1 加密货币": {
        "主流币": {
            "比特币": "BTC-USD",
            "以太坊": "ETH-USD",
            "币安币": "BNB-USD",
            "Solana": "SOL-USD",
            "瑞波币": "XRP-USD",
            "狗狗币": "DOGE-USD",
        },
        "ETF": {
            "比特币ETF(IBIT)": "IBIT",
            "比特币ETF(GBTC)": "GBTC",
        },
    },
    "\U0001f4b5 外汇": {
        "主要货币对": {
            "欧元/美元": "EURUSD=X",
            "美元/日元": "JPY=X",
            "英镑/美元": "GBPUSD=X",
            "美元/人民币": "CNY=X",
            "美元/港币": "HKD=X",
            "美元/加元": "CAD=X",
        },
    },
}


def get_market_names() -> List[str]:
    """获取所有市场名称"""
    return list(ASSET_CATALOG.keys())


def search_assets(keyword: str) -> List[Dict]:
    """搜索资产，按名称或代码模糊匹配"""
    results = []
    if not keyword:
        return results
    for market, types in ASSET_CATALOG.items():
        for asset_type, assets in types.items():
            for name, ticker in assets.items():
                if (keyword in name.lower() or
                        keyword in ticker.lower() or
                        keyword in market.lower()):
                    label = f"{market} \u00b7 {asset_type} | {name} ({ticker})"
                    results.append({
                        "market": market,
                        "type": asset_type,
                        "name": name,
                        "ticker": ticker,
                        "label": label,
                    })
    return results


def get_assets_by_market(market: str) -> dict:
    """获取指定市场下的所有资产"""
    return ASSET_CATALOG.get(market, {})


# ============================================================
# Ticker 格式检测与转换
# ============================================================

_HK_INDICES = {"HSI", "HSTECH", "HSCEI"}

_FMP_TICKER_MAP = {
    "^GSPC": "SPY",
    "^IXIC": "QQQ",
    "^DJI":  "DIA",
    "^N225": "EWJ",
    "^GDAXI": "EWG",
    "^FTSE": "EWU",
    "^FCHI": "EWQ",
}

# 新浪全球指数代码映射（用于实时行情和 K 线）
_SINA_GLOBAL_INDEX_MAP = {
    "^GSPC": "int_spx",
    "^IXIC": "int_nasdaq",
    "^DJI": "int_dji",
    "^N225": "int_nikkei",
    "^GDAXI": "int_dax",
    "^FTSE": "int_ftse",
    "^FCHI": "int_cac",
}


def detect_market(ticker: str) -> str:
    """
    检测 ticker 所属类型，返回：
    - "a_share"   : A 股股票/ETF/指数
    - "hk"        : 港股个股
    - "hk_index"  : 港股指数（HSI / HSTECH / HSCEI）
    - "us"        : 美股股票/ETF
    - "global_idx": 全球指数（^N225、^GDAXI 等）
    - "futures"   : 期货（GC=F、CL=F 等）
    - "crypto"    : 加密货币（BTC-USD 等）
    - "forex"     : 外汇（EURUSD=X 等）
    """
    t = ticker.strip().upper()

    # 处理 yfinance 风格的 A 股后缀（.SS = 上海, .SZ = 深圳, .SH = 上海）
    if re.match(r'^\d{6}\.(SS|SZ|SH)$', t):
        return "a_share"
    if t.startswith("SH") or t.startswith("SZ"):
        return "a_share"
    if re.match(r'^\d{6}$', t):
        return "a_share"
    if t in _HK_INDICES:
        return "hk_index"
    if re.match(r'^\d{5}$', t):
        return "hk"
    if t.startswith("^"):
        return "global_idx"
    if "=F" in t:
        return "futures"
    if "=X" in t or t.startswith("DX-"):
        return "forex"
    if re.search(r'-(USD[T]?|BUSD)$', t):
        return "crypto"
    return "us"


def normalize_ticker_for_akshare(ticker: str) -> str:
    """将用户输入的 ticker 转换为 akshare 需要的格式"""
    t = ticker.strip()
    market = detect_market(t)

    if market == "a_share":
        t_upper = t.upper()
        # 优先根据 .SS/.SZ 后缀判断交易所
        if t_upper.endswith(".SS") or t_upper.endswith(".SH"):
            code = re.sub(r'\.(SS|SH)$', '', t_upper)
            return f"sh{code}"
        elif t_upper.endswith(".SZ"):
            code = re.sub(r'\.SZ$', '', t_upper)
            return f"sz{code}"
        # SH/SZ 前缀
        if t_upper.startswith("SH") or t_upper.startswith("SZ"):
            return t_upper.lower()
        # 纯数字：6开头=上海，其余=深圳
        t_clean = t_upper.replace("SH", "").replace("SZ", "")
        if t_clean.startswith("6"):
            return f"sh{t_clean}"
        else:
            return f"sz{t_clean}"
    elif market in ("hk", "hk_index"):
        return t.zfill(5) if market == "hk" else t.upper()
    else:
        return t.upper()


def normalize_display_name(ticker: str) -> str:
    """返回用于显示的标准化名称"""
    t = ticker.strip()
    market = detect_market(t)
    if market == "a_share":
        t_upper = t.upper()
        # 已经有交易所前缀
        if t_upper.startswith(("SH", "SZ")):
            return t_upper
        # 根据 .SS/.SZ 后缀判断
        if t_upper.endswith(".SS") or t_upper.endswith(".SH"):
            code = re.sub(r'\.(SS|SH)$', '', t_upper)
            return f"SH{code}"
        if t_upper.endswith(".SZ"):
            code = re.sub(r'\.SZ$', '', t_upper)
            return f"SZ{code}"
        # 纯数字：6开头=上海，其余=深圳
        return f"SH{t}" if t.startswith("6") else f"SZ{t}"
    return t


# ============================================================
# 数据源 0：新浪财经（不依赖 eastmoney，最可靠）
# ============================================================

def _sina_kline_a_share(ticker: str) -> pd.DataFrame:
    """
    新浪财经 A 股/指数历史 K 线（不走 eastmoney）
    免费、无需 API Key、每天最多 1500 条
    """
    norm = normalize_ticker_for_akshare(ticker)  # e.g. "sh000300"
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": norm, "scale": "240", "ma": "no", "datalen": "1500"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200 or not resp.text.strip():
            return pd.DataFrame()
        data = resp.json()
        if not data or not isinstance(data, list):
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df = df.rename(columns={"day": "date"})
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = df["close"].astype(float)
        df = df.set_index("date")[["close"]]
        df = df.sort_index()
        return df
    except Exception as e:
        print(f"  新浪A股K线失败 {ticker}: {e}")
        return pd.DataFrame()


def _sina_kline_us(ticker: str) -> pd.DataFrame:
    """
    新浪财经美股历史 K 线（不走 eastmoney）
    """
    url = "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/data/US_MinKService.getDailyK"
    params = {"symbol": ticker.upper(), "datalen": "5000"}
    try:
        resp = requests.get(url, params=params, timeout=15,
                            headers={"Referer": "https://finance.sina.com.cn"})
        if resp.status_code != 200 or len(resp.text) < 100:
            return pd.DataFrame()
        match = re.search(r'\[.*\]', resp.text, re.DOTALL)
        if not match:
            return pd.DataFrame()
        data = json.loads(match.group())
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df = df.rename(columns={"d": "date", "c": "close"})
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = df["close"].astype(float)
        df = df.set_index("date")[["close"]]
        df = df.sort_index()
        return df
    except Exception as e:
        print(f"  新浪美股K线失败 {ticker}: {e}")
        return pd.DataFrame()


def _download_sina(market: str, ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    新浪财经统一下载入口（瀑布第一层，不走 eastmoney）
    支持：A 股个股、A 股指数、美股、ETF
    """
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    if market == "a_share":
        df = _sina_kline_a_share(ticker)
    elif market == "us":
        df = _sina_kline_us(ticker)
    else:
        # 新浪暂不支持港股历史、期货、加密等
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    df = df.loc[start_dt:end_dt]
    return df if not df.empty else pd.DataFrame()


# ============================================================
# 数据源 0.5：NASDAQ 官方 API（美股备用）
# ============================================================

def _download_nasdaq_api(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    使用 NASDAQ 官方 API 下载美股数据（免费，无需 API Key）
    仅支持美股/ETF
    """
    market = detect_market(ticker)
    if market not in ("us",):
        return pd.DataFrame()

    try:
        start_fmt = pd.Timestamp(start).strftime("%Y-%m-%d")
        url = f"https://api.nasdaq.com/api/quote/{ticker.upper()}/historical"
        params = {"assetclass": "etf", "fromdate": start_fmt, "limit": "5000"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()
        rows = data.get("data", {}).get("tradesTable", {}).get("rows", [])
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = df["close"].astype(str).str.replace(",", "").astype(float)
        df = df.set_index("date").sort_index()

        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        df = df.loc[start_dt:end_dt, ["close"]]
        return df if not df.empty else pd.DataFrame()

    except Exception as e:
        print(f"  NASDAQ API 失败 {ticker}: {e}")
        return pd.DataFrame()


# ============================================================
# 数据源 1：efinance（东方财富接口，国内最全，需绕过代理）
# ============================================================

# efinance ticker 格式映射（efinance 使用东方财富 secid）
_EFINANCE_GLOBAL_MAP = {
    "^GSPC": "100.SPX",
    "^IXIC": "100.NDX",
    "^DJI": "100.DJIA",
    "^N225": "100.N225",
    "^GDAXI": "100.GDAXI",
    "^FTSE": "100.FTSE",
    "^FCHI": "100.FCHI",
    "^KS11": "100.KS11",
    "^NSEI": "100.NIFTY",
    "^HSI": "100.HSI",
    "^HSTECH": "100.HSTECH",
    "^HSCEI": "100.HSCEI",
}


def _to_efinance_code(ticker: str, market: str) -> str:
    """将 ticker 转换为 efinance get_quote_history 需要的代码"""
    t = ticker.strip()

    if market == "a_share":
        # efinance 支持纯数字代码（如 000300, 600519, 510300）
        # 先去除 .SS/.SZ/.SH 后缀，再去除 SH/SZ 前缀
        code = re.sub(r'\.(SS|SZ|SH)$', '', t.upper()).replace("SH", "").replace("SZ", "")
        return code
    elif market in ("hk", "hk_index"):
        # efinance 支持 5 位港股代码（如 00700, HSI）
        if market == "hk_index":
            return t.upper()  # HSI, HSTECH, HSCEI
        return t.zfill(5)
    elif market == "us":
        return t.upper()  # AAPL, SPY, QQQ 等
    elif market == "global_idx":
        # 全球指数需要特殊映射
        mapped = _EFINANCE_GLOBAL_MAP.get(t.upper())
        if mapped:
            return mapped
        return t.upper().lstrip("^")
    elif market == "futures":
        # 期货代码：GC=F -> GC00Y 等
        symbol = t.upper().replace("=F", "").replace("=f", "")
        return f"{symbol}00Y"
    elif market == "crypto":
        return t.upper().replace("-USD", "USD")
    elif market == "forex":
        return t.upper().replace("=X", "")
    return t


def _download_efinance(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    使用 efinance 下载数据（东方财富接口，国内最全面）
    覆盖 A股/港股/美股/全球指数/期货/外汇
    需绕过系统代理
    """
    import efinance as ef

    market = detect_market(ticker)
    code = _to_efinance_code(ticker, market)

    beg = start.replace("-", "")
    fin = end.replace("-", "")

    try:
        df = ef.stock.get_quote_history(code, beg=beg, end=fin)
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # 标准化列名
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "close" in cl or "收盘" in cl:
            col_map[c] = "close"
        elif "date" in cl or "日期" in cl:
            col_map[c] = "date"

    if "close" not in col_map.values():
        return pd.DataFrame()

    df = df.rename(columns=col_map)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    else:
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"

    result = df[["close"]].copy()
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna().sort_index()
    return result


# ============================================================
# 数据源 1：AKShare
# ============================================================
def _download_a_share(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载 A 股个股数据（东方财富接口）"""
    import akshare as ak

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
    """下载港股个股数据"""
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


def _download_hk_index(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载港股指数数据（HSI/HSTECH/HSCEI），尝试多种方式"""
    # 方法 1: AKShare 东方财富接口
    try:
        import akshare as ak
        code = ticker.upper()
        df = ak.stock_hk_index_daily_em(symbol=code)
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
            else:
                df.index = pd.to_datetime(df.index)
                df.index.name = "date"
            start_dt = pd.Timestamp(start)
            end_dt = pd.Timestamp(end)
            df = df.loc[start_dt:end_dt, ["close"]]
            if not df.empty:
                return df
    except Exception as e:
        print(f"  AKShare 港股指数下载失败 {ticker}: {e}")

    # 方法 2: yfinance (恒生指数 ^HSI)
    yf_map = {"HSI": "^HSI", "HSTECH": "^HSTECH", "HSCEI": "^HSCEI"}
    yf_ticker = yf_map.get(ticker.upper())
    if yf_ticker:
        df = _download_yfinance(yf_ticker, start, end)
        if not df.empty:
            return df

    return pd.DataFrame()


def _download_us(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载美股数据"""
    import akshare as ak

    code = ticker.upper()
    df = ak.stock_us_daily(symbol=code, adjust="qfq")
    if df is None or df.empty:
        code_alt = code.replace(".", "-")
        if code_alt != code:
            df = ak.stock_us_daily(symbol=code_alt, adjust="qfq")
        if df is None or df.empty:
            return pd.DataFrame()

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


def _download_global_index(ticker: str, start: str, end: str) -> pd.DataFrame:
    """下载全球指数数据（多源回退：yfinance → stooq → AKShare）
    
    全球指数（^GSPC, ^IXIC, ^N225 等）的特殊处理：
    1. yfinance 使用 trust_env=False 绕过系统代理
    2. stooq.com 免费 CSV 接口作为备选
    3. AKShare 的 stock_us_index_daily 仅支持美股指数
    """
    import io
    
    # ========== 方法 1: yfinance (无 session，让 yfinance 自行处理) ==========
    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(start=start, end=end, auto_adjust=True)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close_col = None
            for c in df.columns:
                if c.lower() == "close":
                    close_col = c
                    break
            if close_col:
                result = df[[close_col]].copy()
                result.columns = ["close"]
                result.index = pd.to_datetime(result.index)
                result.index.name = "date"
                if not result.empty:
                    return result
    except Exception as e:
        print(f"  yfinance 全球指数失败 {ticker}: {e}")

    # ========== 方法 2: stooq.com 免费 CSV 接口 ==========
    try:
        # stooq 使用反向 ticker 格式: ^GSPC -> ^spx, ^IXIC -> ^ndq
        stooq_map = {
            "^GSPC": "^spx", "^IXIC": "^ndq", "^DJI": "^dji",
            "^N225": "^nkx", "^GDAXI": "^dax", "^FTSE": "^ftse",
            "^FCHI": "^cac", "^KS11": "^kospi", "^NSEI": "^nifty",
        }
        stooq_ticker = stooq_map.get(ticker, ticker.lower())
        
        start_fmt = pd.Timestamp(start).strftime("%Y-%m-%d")
        end_fmt = pd.Timestamp(end).strftime("%Y-%m-%d")
        
        url = f"https://stooq.com/q/d/l/?s={stooq_ticker}&d1={start_fmt}&d2={end_fmt}&i=d"
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        if resp.status_code == 200 and len(resp.text) > 50:
            df = pd.read_csv(io.StringIO(resp.text))
            if "Date" in df.columns and "Close" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date")
                df = df[["Close"]].rename(columns={"Close": "close"})
                df = df.dropna()
                if not df.empty:
                    print(f"  ✓ {ticker}: stooq成功, {len(df)} 条")
                    return df
    except Exception as e:
        print(f"  stooq 全球指数失败 {ticker}: {e}")

    # ========== 方法 3: AKShare stock_us_daily (ETF 等效法) ==========
    # 全球指数没有直接 API，用跟踪 ETF 代替：
    # ^GSPC → SPY, ^IXIC → QQQ, ^DJI → DIA, ^N225 → EWJ, 等
    try:
        import akshare as ak
        etf_equivalent_map = {
            "^GSPC": "SPY", "^IXIC": "QQQ", "^DJI": "DIA",
            "^N225": "EWJ", "^GDAXI": "EWG", "^FTSE": "EWU",
            "^FCHI": "EWQ", "^KS11": "EWY", "^NSEI": "INDA",
        }
        etf_ticker = etf_equivalent_map.get(ticker)
        if etf_ticker:
            df = ak.stock_us_daily(symbol=etf_ticker, adjust="qfq")
            if df is not None and not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["close"]]
                start_dt = pd.Timestamp(start)
                end_dt = pd.Timestamp(end)
                df = df.loc[start_dt:end_dt]
                if not df.empty:
                    print(f"  ✓ {ticker}: AKShare ETF等效({etf_ticker})成功, {len(df)} 条")
                    return df
    except Exception as e:
        print(f"  AKShare ETF等效失败 {ticker}: {e}")

    # ========== 方法 4: AKShare index_global_hist_em (东方财富全球指数) ==========
    try:
        import akshare as ak
        global_idx_map = {
            "^FTSE": "UKX", "^GDAXI": "DAX", "^FCHI": "CAC",
            "^N225": "NKY", "^KS11": "KOSPI",
        }
        ak_code = global_idx_map.get(ticker)
        if ak_code:
            df = ak.index_global_hist_em(symbol=ak_code)
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
                start_dt = pd.Timestamp(start)
                end_dt = pd.Timestamp(end)
                df = df.loc[start_dt:end_dt, ["close"]]
                if not df.empty:
                    print(f"  ✓ {ticker}: AKShare index_global_hist_em({ak_code})成功, {len(df)} 条")
                    return df
    except Exception as e:
        print(f"  AKShare index_global_hist_em 失败 {ticker}: {e}")

    return pd.DataFrame()


def _download_akshare_by_market(market: str, norm: str, start: str, end: str) -> pd.DataFrame:
    """统一的 akshare 下载入口"""
    if market == "a_share":
        code = norm.lower().replace("sh", "").replace("sz", "")
        if code.startswith("000") or code.startswith("399"):
            try:
                df = _download_a_share_index(norm, start, end)
            except Exception:
                import akshare as ak
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
    elif market == "hk_index":
        df = _download_hk_index(norm, start, end)
    elif market == "global_idx":
        # AKShare 没有通用的全球指数日线接口，跳过
        return pd.DataFrame()
    elif market == "futures":
        # 尝试 AKShare 期货接口
        import akshare as ak
        symbol = norm.upper().replace("=F", "")
        futures_map = {
            "GC": "GC", "CL": "CL", "SI": "SI", "HG": "HG",
            "NG": "NG", "ZC": "ZC", "ZW": "ZW", "ZS": "ZS",
            "PL": "PL", "BZ": "BZ",
        }
        fmp_sym = futures_map.get(symbol, symbol)
        try:
            df = ak.futures_foreign_hist(symbol=fmp_sym)
            if df is not None and not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["close"]]
                df["close"] = df["close"].astype(float)
                start_dt = pd.Timestamp(start)
                end_dt = pd.Timestamp(end)
                df = df.loc[start_dt:end_dt]
        except Exception:
            return pd.DataFrame()
    elif market in ("crypto", "forex"):
        # AKShare 不支持，跳过到 yfinance
        return pd.DataFrame()
    else:
        df = _download_us(norm, start, end)

    if df is not None and not df.empty:
        return df
    return pd.DataFrame()


# ============================================================
# 数据源 2：yfinance（通用回退）
# ============================================================
def _download_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame:
    """使用 yfinance 下载数据（通用回退方案）
    
    注意: 新版 yfinance 使用 curl_cffi，不接受 requests.Session。
    直接调用 yf.Ticker()，不传 session，让 yfinance 自行处理网络连接。
    """
    import yfinance as yf

    yf_ticker = ticker.strip()
    
    try:
        ticker_obj = yf.Ticker(yf_ticker)
        df = ticker_obj.history(start=start, end=end, auto_adjust=True)
    except Exception:
        # 回退到全局 download 函数
        df = yf.download(yf_ticker, start=start, end=end, progress=False, auto_adjust=True)

    if df is None or df.empty:
        return pd.DataFrame()

    # 处理 MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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


# ============================================================
# 数据源 3：FMP（Financial Modeling Prep）免费 API
# ============================================================
def _download_fmp(ticker: str, start: str, end: str) -> pd.DataFrame:
    """使用 FMP API 下载数据（第三回退方案）"""
    if not FMP_API_KEY:
        return pd.DataFrame()

    market = detect_market(ticker)
    fmp_symbol = ticker.upper()

    if market == "global_idx":
        fmp_symbol = _FMP_TICKER_MAP.get(ticker.upper(), ticker.upper().lstrip("^"))
    elif market == "futures":
        fmp_symbol = ticker.upper().replace("=F", "").replace("=f", "") + "USD"
    elif market == "crypto":
        fmp_symbol = ticker.upper().replace("-USD", "USD").replace("-USDT", "USD")
    elif market == "hk":
        fmp_symbol = f"{ticker.zfill(5)}.HK"
    elif market == "hk_index":
        fmp_symbol = f"^{ticker.upper()}"
    elif market == "forex":
        fmp_symbol = ticker.upper().replace("=X", "")

    try:
        url = f"{FMP_BASE_URL}/historical-price-full/{fmp_symbol}"
        params = {"from": start, "to": end, "apikey": FMP_API_KEY}
        resp = requests.get(url, params=params, timeout=30)

        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()
        if "historical" not in data or not data["historical"]:
            return pd.DataFrame()

        df = pd.DataFrame(data["historical"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df[["close"]]
        return df

    except Exception as e:
        print(f"FMP 下载失败 {ticker} -> {fmp_symbol}: {e}")
        return pd.DataFrame()


# ============================================================
# 主下载函数：瀑布式回退
# ============================================================
def download_data(
    tickers: List[str],
    start: str,
    end: str,
    cache_dir: str = "data",
) -> Tuple[pd.DataFrame, List[str]]:
    """
    下载多只标的的日线收盘价数据。

    下载瀑布（按可靠性排序）：
    1. 新浪财经（A股/美股，不走 eastmoney，最可靠）
    2. AKShare（东方财富后端，国内最强，但可能被代理阻断）
    3. yfinance（全球通用，但国内需梯子）
    4. FMP（需 API Key，最后兜底）

    Returns:
        prices_df: 收盘价 DataFrame，index=date, columns=tickers
        invalid: 无法下载数据的 ticker 列表
    """
    os.makedirs(cache_dir, exist_ok=True)
    all_prices = {}
    invalid = []

    for ticker in tickers:
        ticker = ticker.strip()
        if not ticker:
            continue

        norm = normalize_ticker_for_akshare(ticker)
        display = normalize_display_name(ticker)
        market = detect_market(ticker)

        cache_file = os.path.join(cache_dir, f"{norm}_{start}_{end}.parquet")

        # 检查本地缓存
        if os.path.exists(cache_file):
            try:
                df = pd.read_parquet(cache_file)
                if not df.empty:
                    all_prices[ticker] = df["close"]
                    continue
            except Exception:
                pass

        df = pd.DataFrame()

        # ===== 瀑布式回退下载（按可靠性排序） =====
        sources_tried = []

        # 第0层：全球指数专用下载器（yfinance→stooq→AKShare 三重回退）
        if market == "global_idx":
            sources_tried.append("全球指数专用")
            try:
                df = _download_global_index(ticker, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: 全球指数专用下载成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: 全球指数专用下载失败 - {e}")

        # 第0.5层：新浪财经（不走 eastmoney，国内最可靠）
        if df.empty and market in ("a_share", "us"):
            sources_tried.append("新浪财经")
            try:
                df = _download_sina(market, ticker, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: 新浪财经成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: 新浪财经失败 - {e}")

        # 第1层：efinance（东方财富，国内最全面，需绕过代理）
        if df.empty:
            sources_tried.append("efinance")
            try:
                df = _bypass_proxy(_download_efinance, ticker, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: efinance成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: efinance失败 - {e}")

        # 第2层：NASDAQ 官方 API（仅美股）
        if df.empty and market == "us":
            sources_tried.append("NASDAQ API")
            try:
                df = _download_nasdaq_api(ticker, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: NASDAQ API成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: NASDAQ API失败 - {e}")

        # 第3层：AKShare（东方财富后端，需绕过代理）
        if df.empty and market in ("a_share", "hk", "hk_index", "us", "futures", "global_idx"):
            sources_tried.append("AKShare")
            try:
                df = _bypass_proxy(_download_akshare_by_market, market, norm, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: AKShare成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: AKShare失败 - {e}")

        # 第4层：yfinance（全球通用，国内可能被限频）
        if df.empty:
            sources_tried.append("yfinance")
            try:
                yf_ticker = ticker
                if market == "global_idx":
                    pass  # yfinance 直接支持 ^GSPC 等
                elif market == "hk":
                    yf_ticker = f"{ticker.zfill(5)}.HK"
                df = _download_yfinance(yf_ticker, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: yfinance成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: yfinance失败 - {e}")

        # 第5层：FMP API（需 API Key）
        if df.empty:
            sources_tried.append("FMP")
            try:
                df = _download_fmp(ticker, start, end)
                if not df.empty:
                    print(f"  ✓ {display}: FMP成功, {len(df)} 条")
            except Exception as e:
                print(f"  ✗ {display}: FMP失败 - {e}")

        # 处理结果
        if df.empty:
            invalid.append(ticker)
            print(f"  ✗ {display}: 所有数据源均失败 ({', '.join(sources_tried)})")
        else:
            # 确保数据类型正确
            df = df[["close"]].copy()
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["close"])
            df = df.sort_index()

            # 缓存到本地
            try:
                df.to_parquet(cache_file)
            except Exception:
                pass

            all_prices[ticker] = df["close"]

    if not all_prices:
        return pd.DataFrame(), invalid

    # 合并为 DataFrame，前向填充缺失值（不同市场的交易日不同）
    prices = pd.DataFrame(all_prices)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()
    prices = prices.ffill().bfill()

    # 统一清洗：确保扁平列名、唯一列名、全数值
    prices = _clean_prices_df(prices)

    return prices, invalid


# ============================================================
# 组合收益计算（纯 pandas/numpy，无 vectorbt 依赖）
# ============================================================
def calculate_portfolio_returns(
    prices: pd.DataFrame,
    weights: List[float],
    rebalance: str = "无",
) -> pd.Series:
    """
    计算组合每日回报率（纯 pandas/numpy 实现，无需 vectorbt）

    Args:
        prices: 收盘价 DataFrame，index=date, columns=tickers
        weights: 权重列表（与 prices.columns 对应），会自动归一化
        rebalance: 再平衡频率 "无" / "每月" / "每季度"

    Returns:
        组合每日回报率 Series
    """
    if prices.empty or (hasattr(weights, '__len__') and len(weights) == 0):
        return pd.Series(dtype=float)

    # 扁平化 MultiIndex 列（yfinance 可能返回多层列名）
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(0)

    # 权重归一化
    w = np.array(weights, dtype=float)
    w = w / w.sum()

    # 防御性检查：列数与权重数必须一致
    n_cols = len(prices.columns)
    n_weights = len(w)
    if n_cols != n_weights:
        print(f"  ⚠️ 列数 ({n_cols}) != 权重数 ({n_weights})，截取前 {min(n_cols, n_weights)} 个")
        n = min(n_cols, n_weights)
        prices = prices.iloc[:, :n]
        w = w[:n]
        w = w / w.sum()  # 重新归一化

    if prices.empty:
        return pd.Series(dtype=float)

    # 计算每日个股回报率
    daily_returns = prices.pct_change().dropna()
    if daily_returns.empty:
        return pd.Series(dtype=float)

    if rebalance == "无":
        # 简单加权：buy and hold（权重随涨跌自然偏移）
        portfolio_returns = (daily_returns * w).sum(axis=1)
    else:
        # 再平衡模式：在再平衡日重置权重
        if rebalance == "每月":
            rebal_dates = daily_returns.resample("M").last().index
        elif rebalance == "每季度":
            rebal_dates = daily_returns.resample("Q").last().index
        else:
            rebal_dates = daily_returns.resample("M").last().index

        # 找到每个再平衡日在 daily_returns 中的实际位置
        rebal_mask = daily_returns.index.isin(rebal_dates)

        # 用累计回报追踪权重变化，再平衡时重置
        # 权重跟踪法
        portfolio_values = [1.0]
        current_w = w.copy()
        asset_values = w.copy()  # 各资产当前价值占比

        for i in range(len(daily_returns)):
            date = daily_returns.index[i]
            day_ret = daily_returns.iloc[i].values

            # 更新各资产价值
            asset_values = asset_values * (1 + day_ret)
            total_value = asset_values.sum()

            # 当日组合回报
            portfolio_returns_today = total_value / portfolio_values[-1] - 1
            portfolio_values.append(total_value)
            current_w = asset_values / total_value

            # 再平衡日：重置权重
            if rebal_mask[i]:
                asset_values = w * total_value
                current_w = w.copy()

        portfolio_returns = pd.Series(
            [portfolio_values[i+1] / portfolio_values[i] - 1 for i in range(len(daily_returns))],
            index=daily_returns.index,
        )

    return portfolio_returns


def calculate_benchmark_returns(prices_series: pd.Series) -> pd.Series:
    """
    计算单资产基准的日收益率

    Args:
        prices_series: 价格序列（Series，index=date）

    Returns:
        日收益率 Series
    """
    if prices_series.empty:
        return pd.Series(dtype=float)
    returns = prices_series.pct_change().dropna()
    return returns


def calculate_benchmark_portfolio_returns(
    prices: pd.DataFrame,
    weights: List[float],
) -> pd.Series:
    """
    计算多资产基准组合的日收益率（买入持有，不进行再平衡）

    Args:
        prices: 价格 DataFrame，index=date, columns=tickers
        weights: 权重列表

    Returns:
        日收益率 Series
    """
    if prices.empty or (hasattr(weights, '__len__') and len(weights) == 0):
        return pd.Series(dtype=float)

    # 扁平化 MultiIndex 列（yfinance 可能返回多层列名）
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(0)

    w = np.array(weights, dtype=float)
    if w.size == 0:
        return pd.Series(dtype=float)
    w = w / w.sum()

    # 防御性检查：列数与权重数必须一致
    n_cols = len(prices.columns)
    n_weights = len(w)
    if n_cols != n_weights:
        print(f"  ⚠️ 基准: 列数 ({n_cols}) != 权重数 ({n_weights})，截取前 {min(n_cols, n_weights)} 个")
        n = min(n_cols, n_weights)
        prices = prices.iloc[:, :n]
        w = w[:n]
        w = w / w.sum()  # 重新归一化

    if prices.empty:
        return pd.Series(dtype=float)

    daily_returns = prices.pct_change().dropna()
    if daily_returns.empty:
        return pd.Series(dtype=float)

    # 使用 numpy 矩阵乘法避免 pandas 列名对齐问题（MultiIndex 等）
    portfolio_returns = pd.Series(
        daily_returns.values @ w,
        index=daily_returns.index,
        name="benchmark_returns",
    )
    return portfolio_returns


def compute_metrics(returns: pd.Series, risk_free_rate: float = 0.02) -> Dict[str, float]:
    """
    计算关键绩效指标

    Args:
        returns: 每日回报率 Series
        risk_free_rate: 年化无风险利率（默认 2%）

    Returns:
        指标字典
    """
    if returns.empty or len(returns) < 2:
        return {}

    total_days = len(returns)
    years = total_days / 252

    # 总回报
    total_return = (1 + returns).prod() - 1
    # 年化回报
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    # 年化波动率
    annual_vol = returns.std() * np.sqrt(252)
    # Sharpe 比率
    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else 0
    # Sortino 比率
    downside = returns[returns < 0]
    downside_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 0
    sortino = (annual_return - risk_free_rate) / downside_vol if downside_vol > 0 else 0
    # 最大回撤
    cum = (1 + returns).cumprod()
    drawdown = (cum - cum.cummax()) / cum.cummax()
    max_drawdown = drawdown.min()
    # Calmar 比率
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
    # 胜率
    win_rate = (returns > 0).sum() / total_days if total_days > 0 else 0
    # 盈亏比
    avg_win = returns[returns > 0].mean() if (returns > 0).any() else 0
    avg_loss = abs(returns[returns < 0].mean()) if (returns < 0).any() else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    return {
        "总回报": f"{total_return:.2%}",
        "年化回报": f"{annual_return:.2%}",
        "年化波动率": f"{annual_vol:.2%}",
        "Sharpe比率": f"{sharpe:.2f}",
        "Sortino比率": f"{sortino:.2f}",
        "最大回撤": f"{max_drawdown:.2%}",
        "Calmar比率": f"{calmar:.2f}",
        "胜率": f"{win_rate:.2%}",
        "盈亏比": f"{profit_loss_ratio:.2f}",
        "交易天数": total_days,
        "回测年数": f"{years:.1f}",
    }


def compute_metrics_for_display(
    portfolio_returns: pd.Series,
    benchmark_returns: Optional[pd.Series],
) -> pd.DataFrame:
    """计算并格式化指标表格（用于 Streamlit 展示）"""
    rows = []

    p_metrics = compute_metrics(portfolio_returns)
    p_row = {"组合": "投资组合"}
    p_row.update(p_metrics)
    rows.append(p_row)

    if benchmark_returns is not None and len(benchmark_returns) > 1:
        b_metrics = compute_metrics(benchmark_returns)
        b_row = {"组合": "基准"}
        b_row.update(b_metrics)
        rows.append(b_row)

        # 超额指标
        try:
            excess_annual = float(p_metrics.get("年化回报", "0%").rstrip("%")) / 100 - \
                            float(b_metrics.get("年化回报", "0%").rstrip("%")) / 100
            excess_sharpe = float(p_metrics.get("Sharpe比率", "0")) - \
                           float(b_metrics.get("Sharpe比率", "0"))
            excess_row = {"组合": "超额收益",
                          "年化回报": f"{excess_annual:.2%}",
                          "Sharpe比率": f"{excess_sharpe:.2f}"}
            rows.append(excess_row)
        except Exception:
            pass

    return pd.DataFrame(rows)


# ============================================================
# Plotly 交互式图表
# ============================================================
def plot_equity_curve(
    portfolio_cum: pd.Series,
    benchmark_cum: Optional[pd.Series] = None,
    hedge_cum: Optional[pd.Series] = None,
    title: str = "权益曲线",
) -> go.Figure:
    """绘制交互式权益曲线"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=portfolio_cum.index, y=portfolio_cum.values,
        name="投资组合", line=dict(color="#1f77b4", width=2.5),
        hovertemplate="日期: %{x}<br>净值: %{y:.4f}<extra></extra>",
    ))
    if benchmark_cum is not None and len(benchmark_cum) > 0:
        fig.add_trace(go.Scatter(
            x=benchmark_cum.index, y=benchmark_cum.values,
            name="基准指数", line=dict(color="#ff7f0e", width=2, dash="dash"),
            hovertemplate="日期: %{x}<br>净值: %{y:.4f}<extra></extra>",
        ))
    if hedge_cum is not None and len(hedge_cum) > 0:
        fig.add_trace(go.Scatter(
            x=hedge_cum.index, y=hedge_cum.values,
            name="含对冲", line=dict(color="#2ca02c", width=2.5),
            hovertemplate="日期: %{x}<br>净值: %{y:.4f}<extra></extra>",
        ))
    fig.update_layout(
        title=title, xaxis_title="日期", yaxis_title="净值",
        hovermode="x unified", template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500, yaxis_type="log",
    )
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05))
    return fig


def plot_drawdown(returns: pd.Series, benchmark_returns: Optional[pd.Series] = None) -> go.Figure:
    """绘制回撤图"""
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
    """绘制月度收益热力图"""
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
    """绘制年度收益柱状图"""
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


def plot_allocations_pie(tickers: List[str], weights: List[float]) -> go.Figure:
    """绘制资产配置饼图"""
    color_palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    ]
    fig = go.Figure(data=[go.Pie(
        labels=[normalize_display_name(t) for t in tickers],
        values=weights, hole=0.4,
        textinfo="label+percent", textposition="outside",
        marker=dict(colors=color_palette[:len(tickers)]),
    )])
    fig.update_layout(title="资产配置", template="plotly_white", height=400)
    return fig


# ============================================================
# 压力测试
# ============================================================
def stress_test(
    portfolio_returns: pd.Series,
    benchmark_returns: Optional[pd.Series],
    events: Dict[str, Dict],
) -> pd.DataFrame:
    """压力测试：计算各事件下组合和基准的回报和回撤"""
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
    """压力测试柱状图"""
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
    """计算加入对冲资产后的组合回报"""
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
    """生成完整 HTML 报告"""
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