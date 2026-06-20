"""测试替代数据源"""
import os
import sys
import time

for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# 测试 1: yfinance (单个请求，避免限频)
print("=== yfinance 测试 (单个请求) ===")
try:
    import yfinance as yf
    spy = yf.download("SPY", start="2024-01-01", end="2024-01-15", progress=False)
    if not spy.empty:
        print(f"  ✓ SPY: {len(spy)} 条")
        print(f"    {spy.head(3)}")
    else:
        print("  ✗ SPY: 无数据")
except Exception as e:
    print(f"  ✗ yfinance 异常: {e}")

# 测试 2: akshare 新浪后端
print("\n=== akshare 新浪后端测试 ===")
try:
    import akshare as ak
    # 尝试 index_global_hist_sina
    df = ak.index_global_hist_sina(symbol=".N225")
    if not df.empty:
        print(f"  ✓ .N225 via sina: {len(df)} 条")
    else:
        print("  ✗ .N225 via sina: 无数据")
except Exception as e:
    print(f"  ✗ akshare sina 异常: {e}")

# 测试 3: pandas_datareader stooq
print("\n=== pandas_datareader stooq 测试 ===")
try:
    import pandas_datareader.data as web
    df = web.DataReader("SPY", "stooq", start="2024-01-01", end="2024-01-15")
    if not df.empty:
        print(f"  ✓ SPY via stooq: {len(df)} 条")
        print(f"    列: {list(df.columns)}")
    else:
        print("  ✗ SPY via stooq: 无数据")
except ImportError:
    print("  pandas_datareader 未安装")
except Exception as e:
    print(f"  ✗ stooq 异常: {e}")

# 测试 4: 直接用 requests 测试 eastmoney 可达性
print("\n=== 网络连通性测试 ===")
import urllib.request
for host, name in [
    ("push2his.eastmoney.com", "eastmoney"),
    ("query1.finance.yahoo.com", "yahoo finance"),
    ("money.finance.sina.com.cn", "sina finance"),
    ("api.stooq.com", "stooq"),
]:
    try:
        req = urllib.request.Request(f"https://{host}", method="HEAD")
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"  ✓ {name} ({host}): 可达")
    except urllib.error.HTTPError as e:
        print(f"  ✓ {name} ({host}): 可达 (HTTP {e.code})")
    except Exception as e:
        print(f"  ✗ {name} ({host}): 不可达 - {type(e).__name__}")

# 测试 5: A股本地数据 (akshare - 不经过 eastmoney)
print("\n=== akshare 其他后端测试 ===")
try:
    # 尝试 stock_zh_a_hist (这个也是 eastmoney 后端)
    df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20240101", end_date="20240110", adjust="qfq")
    if not df.empty:
        print(f"  ✓ A股 000001: {len(df)} 条")
    else:
        print("  ✗ A股 000001: 无数据")
except Exception as e:
    print(f"  ✗ A股异常: {e}")

# 测试 6: 尝试 pdr_override 让 yfinance 作为 datareader
print("\n=== yfinance as DataReader ===")
try:
    import yfinance as yf
    import pandas_datareader.data as web
    yf.pdr_override()
    df = web.get_data_yahoo("SPY", start="2024-01-01", end="2024-01-15")
    if not df.empty:
        print(f"  ✓ SPY via yf.pdr_override: {len(df)} 条")
    else:
        print("  ✗ 无数据")
except Exception as e:
    print(f"  ✗ 异常: {e}")