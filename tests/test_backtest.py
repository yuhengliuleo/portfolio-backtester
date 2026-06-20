"""
投资组合回测器 - 自动化测试
============================
运行: python -m pytest backtest_app/tests/test_backtest.py -v
"""

import sys
import os
import datetime as dt

import numpy as np
import pandas as pd
import pytest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    _clean_prices_df,
    _bypass_proxy,
    calculate_benchmark_returns,
    calculate_benchmark_portfolio_returns,
    calculate_portfolio_returns,
    compute_metrics,
    compute_metrics_for_display,
    stress_test,
    STRESS_EVENTS,
    detect_market,
    normalize_ticker_for_akshare,
    normalize_display_name,
)


# ============================================================
# Fixtures: 共享测试数据
# ============================================================
@pytest.fixture
def sample_prices():
    """生成测试用价格 DataFrame"""
    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    np.random.seed(42)
    data = {
        "AAPL": 100 * np.cumprod(1 + np.random.normal(0.0005, 0.02, 500)),
        "SPY": 300 * np.cumprod(1 + np.random.normal(0.0003, 0.015, 500)),
        "GLD": 180 * np.cumprod(1 + np.random.normal(0.0002, 0.01, 500)),
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def sample_returns():
    """生成测试用日回报率 Series"""
    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.0005, 0.02, 500), index=dates)
    returns.name = "portfolio"
    return returns


@pytest.fixture
def sample_empty_returns():
    """空回报率 Series"""
    return pd.Series(dtype=float)


# ============================================================
# 测试 _clean_prices_df
# ============================================================
class TestCleanPricesDf:
    def test_normal_df(self, sample_prices):
        """正常 DataFrame 不应被修改"""
        cleaned = _clean_prices_df(sample_prices)
        assert cleaned.shape == sample_prices.shape
        assert list(cleaned.columns) == ["AAPL", "SPY", "GLD"]

    def test_multiindex_columns(self):
        """MultiIndex 列名应被扁平化"""
        dates = pd.date_range("2020-01-01", periods=10, freq="B")
        arrays = [["Close", "Close", "Close"], ["AAPL", "SPY", "GLD"]]
        cols = pd.MultiIndex.from_arrays(arrays)
        df = pd.DataFrame(np.random.randn(10, 3), index=dates, columns=cols)
        cleaned = _clean_prices_df(df)
        # MultiIndex 被扁平化为第一级
        assert "Close" in cleaned.columns or len(cleaned.columns) == 3
        # 应该没有 MultiIndex
        assert not isinstance(cleaned.columns, pd.MultiIndex)

    def test_duplicate_columns(self):
        """重复列名应被去重"""
        dates = pd.date_range("2020-01-01", periods=10, freq="B")
        df = pd.DataFrame(
            np.random.randn(10, 3),
            index=dates,
            columns=["Close", "Close", "Close"],
        )
        cleaned = _clean_prices_df(df)
        assert len(cleaned.columns) == len(set(cleaned.columns))

    def test_string_values(self):
        """非数值数据应被转为 NaN"""
        dates = pd.date_range("2020-01-01", periods=5, freq="B")
        df = pd.DataFrame(
            {"AAPL": [100, "error", 102, 103, 104],
             "SPY": [300, 301, 302, 303, 304]},
            index=dates,
        )
        cleaned = _clean_prices_df(df)
        assert cleaned["AAPL"].dtype in [np.float64, np.float32]
        assert pd.isna(cleaned["AAPL"].iloc[1])

    def test_empty_df(self):
        """空 DataFrame 应返回空"""
        df = pd.DataFrame()
        cleaned = _clean_prices_df(df)
        assert cleaned.empty

    def test_non_datetime_index(self):
        """非 DatetimeIndex 应被转换"""
        df = pd.DataFrame(
            {"A": [1, 2, 3]},
            index=["2020-01-01", "2020-01-02", "2020-01-03"],
        )
        cleaned = _clean_prices_df(df)
        assert isinstance(cleaned.index, pd.DatetimeIndex)


# ============================================================
# 测试 calculate_benchmark_returns
# ============================================================
class TestBenchmarkReturns:
    def test_normal(self, sample_prices):
        """正常计算"""
        returns = calculate_benchmark_returns(sample_prices.iloc[:, 0])
        assert len(returns) > 0
        assert not returns.isna().all()

    def test_empty_series(self):
        """空 Series"""
        returns = calculate_benchmark_returns(pd.Series(dtype=float))
        assert returns.empty


# ============================================================
# 测试 calculate_benchmark_portfolio_returns（核心修复）
# ============================================================
class TestBenchmarkPortfolioReturns:
    def test_normal_multiasset(self, sample_prices):
        """多资产加权计算"""
        w = np.array([0.4, 0.4, 0.2])
        returns = calculate_benchmark_portfolio_returns(sample_prices, w)
        assert len(returns) > 0
        assert not returns.isna().all()

    def test_single_asset(self, sample_prices):
        """单资产（应等同于 pct_change）"""
        single = sample_prices[["AAPL"]]
        w = np.array([1.0])
        returns = calculate_benchmark_portfolio_returns(single, w)
        expected = single.pct_change().dropna()
        np.testing.assert_array_almost_equal(returns.values, expected.values.flatten(), decimal=8)

    def test_with_multiindex_columns(self):
        """MultiIndex 列名（这是之前的崩溃根因）"""
        dates = pd.date_range("2020-01-01", periods=100, freq="B")
        np.random.seed(42)
        arrays = [["Close", "Close"], ["AAPL", "SPY"]]
        cols = pd.MultiIndex.from_arrays(arrays)
        data = pd.DataFrame(
            100 * np.cumprod(1 + np.random.normal(0.001, 0.02, (100, 2)), axis=0),
            index=dates,
            columns=cols,
        )
        w = np.array([0.6, 0.4])
        returns = calculate_benchmark_portfolio_returns(data, w)
        assert len(returns) > 0

    def test_with_duplicate_columns(self):
        """重复列名"""
        dates = pd.date_range("2020-01-01", periods=100, freq="B")
        np.random.seed(42)
        data = pd.DataFrame(
            100 * np.cumprod(1 + np.random.normal(0.001, 0.02, (100, 2)), axis=0),
            index=dates,
            columns=["A", "A"],
        )
        w = np.array([0.5, 0.5])
        # 应该不崩溃
        returns = calculate_benchmark_portfolio_returns(data, w)
        assert len(returns) > 0


# ============================================================
# 测试 calculate_portfolio_returns
# ============================================================
class TestPortfolioReturns:
    def test_no_rebalance(self, sample_prices):
        """无再平衡"""
        w = [0.4, 0.4, 0.2]
        returns = calculate_portfolio_returns(sample_prices, w, "无")
        assert len(returns) > 0

    def test_monthly_rebalance(self, sample_prices):
        """月度再平衡"""
        w = [0.4, 0.4, 0.2]
        returns = calculate_portfolio_returns(sample_prices, w, "每月")
        assert len(returns) > 0

    def test_quarterly_rebalance(self, sample_prices):
        """季度再平衡"""
        w = [0.4, 0.4, 0.2]
        returns = calculate_portfolio_returns(sample_prices, w, "每季度")
        assert len(returns) > 0


# ============================================================
# 测试 compute_metrics（核心修复：签名错误）
# ============================================================
class TestComputeMetrics:
    def test_normal_returns(self, sample_returns):
        """正常回报率"""
        metrics = compute_metrics(sample_returns)
        assert "年化回报" in metrics
        assert "Sharpe比率" in metrics
        assert "最大回撤" in metrics
        assert "胜率" in metrics

    def test_empty_returns(self, sample_empty_returns):
        """空回报率"""
        metrics = compute_metrics(sample_empty_returns)
        assert metrics == {}

    def test_short_returns(self):
        """少于 2 个数据点"""
        returns = pd.Series([0.01])
        metrics = compute_metrics(returns)
        assert metrics == {}

    def test_risk_free_rate_is_float(self, sample_returns):
        """验证 risk_free_rate 参数必须是浮点数"""
        # 正确调用
        metrics = compute_metrics(sample_returns, risk_free_rate=0.03)
        assert "Sharpe比率" in metrics

    def test_string_arg_would_fail(self, sample_returns):
        """验证传字符串给 risk_free_rate 会报错（之前的 bug）"""
        with pytest.raises(TypeError):
            # 之前的错误调用方式
            compute_metrics(sample_returns, risk_free_rate="组合")

    def test_all_zero_returns(self):
        """全零回报率"""
        returns = pd.Series([0.0] * 100)
        metrics = compute_metrics(returns)
        assert metrics["年化回报"] == "0.00%"

    def test_all_negative_returns(self):
        """全负回报率"""
        np.random.seed(42)
        returns = pd.Series(np.random.uniform(-0.05, -0.01, 100))
        metrics = compute_metrics(returns)
        assert "最大回撤" in metrics


# ============================================================
# 测试 compute_metrics_for_display
# ============================================================
class TestMetricsForDisplay:
    def test_with_benchmark(self, sample_returns):
        """含基准（组合 + 基准 + 超额收益 = 3行）"""
        bench_returns = sample_returns * 0.8 + np.random.normal(0, 0.001, len(sample_returns))
        bench_returns.index = sample_returns.index
        df = compute_metrics_for_display(sample_returns, bench_returns)
        assert len(df) == 3  # 组合 + 基准 + 超额收益
        assert "组合" in df.columns

    def test_without_benchmark(self, sample_returns):
        """不含基准"""
        df = compute_metrics_for_display(sample_returns, None)
        assert len(df) == 1
        assert "组合" in df.columns


# ============================================================
# 测试 stress_test
# ============================================================
class TestStressTest:
    def test_with_selected_events(self, sample_returns):
        """选中的压力事件"""
        events = {"2020-COVID": STRESS_EVENTS["2020-COVID"]}
        df = stress_test(sample_returns, None, events)
        # 可能为空（如果回报率数据不覆盖事件时间段），但不应崩溃
        assert isinstance(df, pd.DataFrame)

    def test_empty_events(self, sample_returns):
        """空事件字典"""
        df = stress_test(sample_returns, None, {})
        assert df.empty

    def test_stress_events_valid(self):
        """所有预定义压力事件时间范围有效"""
        for name, info in STRESS_EVENTS.items():
            assert "start" in info, f"{name} 缺少 start"
            assert "end" in info, f"{name} 缺少 end"
            # 验证日期格式
            start = pd.Timestamp(info["start"])
            end = pd.Timestamp(info["end"])
            assert start < end, f"{name}: start 应早于 end"


# ============================================================
# 测试 detect_market
# ============================================================
class TestDetectMarket:
    def test_us_stock(self):
        assert detect_market("AAPL") == "us"

    def test_us_index(self):
        assert detect_market("^GSPC") == "global_idx"

    def test_cn_stock(self):
        assert detect_market("600519") == "a_share"

    def test_cn_index(self):
        assert detect_market("sh000300") == "a_share"

    def test_cn_etf(self):
        assert detect_market("sh510300") == "a_share"

    def test_hk_stock(self):
        assert detect_market("00700") == "hk"

    def test_crypto(self):
        assert detect_market("BTC-USD") == "crypto"

    def test_futures(self):
        assert detect_market("CL=F") == "futures"

    def test_us_short_code(self):
        """短代码如 CL 无 =F 后缀，应归类为 us"""
        assert detect_market("CL") == "us"


# ============================================================
# 测试 _bypass_proxy
# ============================================================
class TestBypassProxy:
    def test_basic_execution(self):
        """基本执行"""
        result = _bypass_proxy(lambda x: x * 2, 5)
        assert result == 10

    def test_with_kwargs(self):
        """带关键字参数"""
        result = _bypass_proxy(lambda a, b=1: a + b, 5, b=3)
        assert result == 8


# ============================================================
# 测试 normalize_ticker_for_akshare
# ============================================================
class TestNormalizeTicker:
    def test_cn_stock(self):
        """A股个股 6开头=上海"""
        result = normalize_ticker_for_akshare("600519")
        assert "600519" in result

    def test_cn_index_sh(self):
        """上证指数"""
        result = normalize_ticker_for_akshare("sh000300")
        assert "000300" in result

    def test_us_stock(self):
        """美股"""
        result = normalize_ticker_for_akshare("AAPL")
        assert result == "AAPL"

    def test_hk_stock(self):
        """港股"""
        result = normalize_ticker_for_akshare("00700")
        assert result == "00700"


# ============================================================
# 测试 normalize_display_name
# ============================================================
class TestNormalizeDisplayName:
    def test_known_ticker(self):
        """已知 ticker"""
        name = normalize_display_name("sh000300")
        assert "300" in name or "沪深" in name

    def test_unknown_ticker(self):
        """未知 ticker 应返回原始值"""
        name = normalize_display_name("UNKNOWN_TICKER")
        assert name == "UNKNOWN_TICKER"


# ============================================================
# 测试 STRESS_EVENTS 定义
# ============================================================
class TestStressEventsDefinition:
    def test_events_not_empty(self):
        assert len(STRESS_EVENTS) > 0

    def test_event_structure(self):
        for name, info in STRESS_EVENTS.items():
            assert "start" in info, f"事件 {name} 缺少 'start'"
            assert "end" in info, f"事件 {name} 缺少 'end'"
            assert "desc" in info, f"事件 {name} 缺少 'desc'"
            # 验证日期格式正确
            pd.Timestamp(info["start"])
            pd.Timestamp(info["end"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])