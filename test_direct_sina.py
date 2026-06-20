"""测试直接通过新浪财经 API 获取全球指数数据"""
import os
import sys
import urllib.request
import json
import re
import csv
from io import StringIO

for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# 新浪财经全球指数代码映射
# 格式: https://hq.sinajs.cn/list=int_nikkei
SINA_GLOBAL_INDEX = {
    "^N225": "int_nikkei",      # 日经225
    "^GSPC": "int_sp500",       # 标普500
    "^IXIC": "int_nasdaq",      # 纳斯达克
    "^DJI":  "int_dji",         # 道琼斯
    "^FTSE": "int_ftse",        # 英国富时100
    "^GDAXI":"int_dax",         # 德国DAX
    "^HSI":  "int_hangseng",    # 恒生指数
}

print("=== 测试新浪全球指数实时行情 ===")
for ticker, sina_code in SINA_GLOBAL_INDEX.items():
    try:
        url = f"https://hq.sinajs.cn/list={sina_code}"
        req = urllib.request.Request(url)
        req.add_header('Referer', 'https://finance.sina.com.cn')
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode('gbk')
        print(f"  {ticker} ({sina_code}): {data[:120]}")
    except Exception as e:
        print(f"  {ticker}: 异常 - {e}")

# 测试新浪历史数据 API
print("\n=== 测试新浪历史数据 API ===")
# https://quotes.sina.cn/cn/api/jsonp.php/var/CN_MarketDataService.getKLineData?symbol=sh000300&scale=240&ma=no&datalen=10
for symbol, name in [("sh000300", "沪深300"), ("sz399001", "深证成指")]:
    try:
        url = f"https://quotes.sina.cn/cn/api/jsonp.php/var/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=30"
        req = urllib.request.Request(url)
        req.add_header('Referer', 'https://finance.sina.com.cn')
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode('utf-8')
        # 解析 JSONP
        json_str = raw[raw.index('(') + 1: raw.rindex(')')]
        data = json.loads(json_str)
        if data:
            print(f"  ✓ {name} ({symbol}): {len(data)} 条")
            print(f"    首条: {data[0]}")
        else:
            print(f"  ✗ {name}: 空数据")
    except Exception as e:
        print(f"  ✗ {name}: {e}")

# 测试新浪美股历史数据
print("\n=== 测试新浪美股历史数据 ===")
# https://finance.sina.com.cn/stock/usstock/sector.shtml
# 历史数据: https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK?symbol=SPY&___qn=3
for symbol, name in [("SPY", "标普500ETF"), ("AAPL", "苹果")]:
    try:
        url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK?symbol={symbol}&___qn=3"
        req = urllib.request.Request(url)
        req.add_header('Referer', 'https://finance.sina.com.cn')
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode('utf-8')
        print(f"  {name} ({symbol}): {raw[:200]}")
    except Exception as e:
        print(f"  ✗ {name}: {e}")

# 测试 yahoo 的 v7/v8 API 直接调用 (绕过 yfinance 限频)
print("\n=== 测试 Yahoo Finance 直接 API ===")
import time
time.sleep(2)  # 等一下避免限频
try:
    ticker = "SPY"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    timestamps = data['chart']['result'][0]['timestamp']
    closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
    print(f"  ✓ SPY 直接API: {len(timestamps)} 条数据")
    print(f"    最新: {closes[-1]}")
except Exception as e:
    print(f"  ✗ Yahoo 直接API: {e}")

# 测试 NASDAQ 数据 API
print("\n=== 测试 NASDAQ 官方 API ===")
try:
    url = "https://api.nasdaq.com/api/quote/SPY/historical?assetclass=etf&fromdate=2024-01-01&limit=30"
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    req.add_header('Accept', 'application/json')
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    rows = data.get('data', {}).get('tradesTable', {}).get('rows', [])
    if rows:
        print(f"  ✓ SPY via NASDAQ: {len(rows)} 条")
        print(f"    首条: {rows[0]}")
    else:
        print(f"  ✗ SPY via NASDAQ: 无数据")
except Exception as e:
    print(f"  ✗ NASDAQ API: {e}")