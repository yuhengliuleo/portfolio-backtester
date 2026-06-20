"""测试全球指数数据下载"""
import os
import sys

# 绕过代理
for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. 测试模块导入
print("=== 模块导入测试 ===")
try:
    import yfinance as yf
    print("✓ yfinance 导入成功")
except ImportError as e:
    print(f"✗ yfinance 导入失败: {e}")

try:
    import efinance as ef
    print("✓ efinance 导入成功")
except ImportError as e:
    print(f"✗ efinance 导入失败: {e}")

import akshare as ak
print("✓ akshare 导入成功")

# 2. 测试 efinance 全球指数
print("\n=== efinance 全球指数测试 ===")
from utils import _bypass_proxy, _download_efinance, _download_yfinance, download_data

test_tickers = {
    "^N225": "日经225",
    "^GSPC": "标普500",
    "^IXIC": "纳斯达克",
    "^DJI": "道琼斯",
}

for ticker, name in test_tickers.items():
    print(f"\n--- {name} ({ticker}) ---")
    try:
        df = _bypass_proxy(_download_efinance, ticker, "2023-01-01", "2024-12-31")
        if not df.empty:
            print(f"  ✓ efinance: {len(df)} 条, 最新: {df['close'].iloc[-1]:.2f}")
        else:
            print(f"  ✗ efinance: 无数据")
    except Exception as e:
        print(f"  ✗ efinance 异常: {e}")

# 3. 测试 yfinance 全球指数
print("\n=== yfinance 全球指数测试 ===")
for ticker, name in test_tickers.items():
    print(f"\n--- {name} ({ticker}) ---")
    try:
        df = _download_yfinance(ticker, "2023-01-01", "2024-12-31")
        if not df.empty:
            print(f"  ✓ yfinance: {len(df)} 条, 最新: {df['close'].iloc[-1]:.2f}")
        else:
            print(f"  ✗ yfinance: 无数据")
    except Exception as e:
        print(f"  ✗ yfinance 异常: {e}")

# 4. 测试完整 download_data 瀑布
print("\n=== 完整 download_data 测试 ===")
for ticker, name in test_tickers.items():
    print(f"\n--- {name} ({ticker}) ---")
    prices, invalid = download_data([ticker], "2023-01-01", "2024-12-31")
    if ticker in invalid:
        print(f"  ✗ 所有数据源均失败")
    elif not prices.empty:
        print(f"  ✓ 成功! {len(prices)} 条数据")
        print(f"    最新日期: {prices.index[-1]}, 收盘价: {prices.iloc[-1, 0]:.2f}")
    else:
        print(f"  ✗ 数据为空")

print("\n=== 测试完成 ===")