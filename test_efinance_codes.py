"""测试 efinance 全球指数正确代码"""
import os
import sys

for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import efinance as ef

# 查看 efinance 支持的全球指数代码
print("=== 测试 efinance 全球指数代码 ===")

# 尝试不同格式
codes_to_try = [
    # 日经225
    ("日经225", ["100.N225", "N225", "100..N225", "int_nikkei", ".N225"]),
    # 标普500
    ("标普500", ["100.SPX", "SPX", "100.SP500", "GSPC", "SPY"]),
    # 纳斯达克
    ("纳斯达克", ["100.NDX", "NDX", "100.IXIC", "IXIC", "QQQ"]),
    # 道琼斯
    ("道琼斯", ["100.DJIA", "DJIA", "100.DJI", "DJI", "DIA"]),
]

for name, codes in codes_to_try:
    print(f"\n--- {name} ---")
    for code in codes:
        try:
            df = ef.stock.get_quote_history(code, beg="20240101", end="20240110")
            if df is not None and not df.empty:
                print(f"  ✓ 代码 '{code}' 有效! {len(df)} 条")
                print(f"    列: {list(df.columns)}")
                print(f"    首行: {df.iloc[0].to_dict()}")
                break
            else:
                print(f"  ✗ 代码 '{code}' 无数据")
        except Exception as e:
            err = str(e)[:80]
            print(f"  ✗ 代码 '{code}' 异常: {err}")
    else:
        print(f"  所有代码均失败")

# 测试 A 股和美股是否正常
print("\n=== 测试基本功能 ===")
for code, name in [("000300", "沪深300"), ("AAPL", "苹果"), ("SPY", "标普500ETF")]:
    try:
        df = ef.stock.get_quote_history(code, beg="20240101", end="20240110")
        if df is not None and not df.empty:
            print(f"  ✓ {name} ({code}): {len(df)} 条")
        else:
            print(f"  ✗ {name} ({code}): 无数据")
    except Exception as e:
        print(f"  ✗ {name} ({code}): {e}")