"""
MiniQMTProvider 集成测试 - 直接调用真实的 xtquant.xtdata

此测试需要：
1. 已安装 xtquant SDK
2. 配置了 QMT 数据路径
3. 有可用的历史数据

运行方式：
    pytest tests/data/providers/test_miniqmt_integration.py -v -s
    pytest tests/data/providers/test_miniqmt_integration.py::test_get_price_real_data -v -s
"""

from datetime import datetime

import pandas as pd
import pytest

from bullet_trade.data.providers.miniqmt import MiniQMTProvider


# 测试标的（选择流动性好的股票）
TEST_STOCKS = {
    "平安银行": "000001.XSHE",
    "浦发银行": "600000.XSHG",
}


def _get_provider():
    """获取真实的 MiniQMTProvider 实例"""
    try:
        provider = MiniQMTProvider({
            "cache_dir": None,  # 测试时不使用缓存
            "mode": "backtest",
        })
        provider.auth()
        return provider
    except ImportError as e:
        pytest.skip(f"xtquant 未安装: {e}")
    except Exception as e:
        pytest.skip(f"MiniQMTProvider 初始化失败: {e}")


@pytest.mark.integration
def test_xtquant_import():
    """测试 xtquant 是否可以正常导入"""
    try:
        from xtquant import xtdata
        assert xtdata is not None
        print(f"✓ xtquant 导入成功")
    except ImportError as e:
        pytest.fail(f"xtquant 导入失败: {e}")


@pytest.mark.integration
def test_get_price_single_stock():
    """测试单只股票数据获取"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        frequency="daily",
        fq="none",
    )
    
    assert not result.empty, "返回数据为空"
    assert "close" in result.columns, "缺少 close 列"
    assert "volume" in result.columns, "缺少 volume 列"
    assert len(result) > 0, "数据条数为 0"
    
    print(f"✓ 获取到 {len(result)} 条日线数据")
    print(f"  日期范围: {result.index[0]} ~ {result.index[-1]}")
    print(f"  收盘价范围: {result['close'].min():.2f} ~ {result['close'].max():.2f}")


@pytest.mark.integration
def test_get_price_multiple_stocks():
    """测试多只股票数据获取"""
    provider = _get_provider()
    
    stocks = list(TEST_STOCKS.values())
    result = provider.get_price(
        stocks,
        start_date="2024-01-01",
        end_date="2024-01-15",
        frequency="daily",
        fq="none",
        panel=True,
    )
    
    assert not result.empty, "返回数据为空"
    assert isinstance(result.columns, pd.MultiIndex), "应该是 MultiIndex"
    
    print(f"✓ 获取到 {len(stocks)} 只股票数据")
    print(f"  股票列表: {result.columns.get_level_values(0).unique().tolist()}")


@pytest.mark.integration
def test_get_price_with_adjustment():
    """测试复权数据"""
    provider = _get_provider()
    
    # 不复权
    result_none = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-06-01",
        end_date="2024-06-30",
        fq="none",
    )
    
    # 前复权
    result_pre = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-06-01",
        end_date="2024-06-30",
        fq="pre",
    )
    
    assert not result_none.empty, "不复权数据为空"
    assert not result_pre.empty, "前复权数据为空"
    
    # 复权后价格应该不同（如果有分红/拆股事件）
    print(f"✓ 不复权收盘价: {result_none['close'].iloc[-1]:.2f}")
    print(f"✓ 前复权收盘价: {result_pre['close'].iloc[-1]:.2f}")


@pytest.mark.integration
def test_get_price_minute_data():
    """测试分钟线数据"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-12-01",
        end_date="2024-12-05",
        frequency="minute",
        fq="none",
    )
    
    assert not result.empty, "分钟线数据为空"
    assert len(result) > 0, "分钟线条数为 0"
    
    print(f"✓ 获取到 {len(result)} 条分钟线数据")


@pytest.mark.integration
def test_get_price_with_count():
    """测试 count 参数"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        count=10,
        frequency="daily",
        fq="none",
    )
    
    assert len(result) == 10, f"应该返回 10 条数据，实际返回 {len(result)} 条"
    print(f"✓ 获取到最近 {len(result)} 条数据")


@pytest.mark.integration
def test_get_price_fields_filter():
    """测试字段过滤"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        fields=["close", "volume"],
        fq="none",
    )
    
    assert list(result.columns) == ["close", "volume"], f"列不匹配: {list(result.columns)}"
    print(f"✓ 字段过滤成功: {list(result.columns)}")


@pytest.mark.integration
def test_get_price_code_normalization():
    """测试股票代码规范化"""
    provider = _get_provider()
    
    # 测试不同格式的代码
    codes = [
        "000001.XSHE",  # 聚宽格式
        "000001.SZ",    # QMT 格式
    ]
    
    for code in codes:
        result = provider.get_price(
            code,
            count=5,
            frequency="daily",
            fq="none",
        )
        assert not result.empty, f"代码 {code} 返回空数据"
    
    print(f"✓ 股票代码规范化正常")


@pytest.mark.integration
def test_get_price_empty_range():
    """测试空日期范围"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2030-01-01",
        end_date="2030-12-31",
        fq="none",
    )
    
    assert result.empty, "未来日期应该返回空数据"
    print(f"✓ 空日期范围处理正常")


@pytest.mark.integration
def test_get_price_skip_paused():
    """测试停牌数据处理"""
    provider = _get_provider()
    
    # skip_paused=True 应该过滤掉 volume=0 的数据
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        fq="none",
        skip_paused=True,
    )
    
    if not result.empty:
        assert (result["volume"] > 0).all(), "skip_paused=True 时应该过滤掉 volume=0 的数据"
    
    print(f"✓ 停牌数据处理正常")


@pytest.mark.integration
def test_get_price_frequency_aliases():
    """测试频率别名"""
    provider = _get_provider()
    
    aliases = ["daily", "day", "1day", "d"]
    
    for alias in aliases:
        result = provider.get_price(
            TEST_STOCKS["平安银行"],
            count=5,
            frequency=alias,
            fq="none",
        )
        assert not result.empty, f"频率别名 {alias} 返回空数据"
    
    print(f"✓ 频率别名测试通过: {aliases}")


@pytest.mark.integration
def test_get_price_datetime_params():
    """测试 datetime 对象作为日期参数"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        fq="none",
    )
    
    assert not result.empty, "datetime 参数返回空数据"
    print(f"✓ datetime 参数测试通过")


@pytest.mark.integration
def test_get_price_performance():
    """测试性能 - 获取大量数据"""
    provider = _get_provider()
    
    import time
    
    start_time = time.time()
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2020-01-01",
        end_date="2024-12-31",
        frequency="daily",
        fq="none",
    )
    elapsed = time.time() - start_time
    
    assert not result.empty, "性能测试数据为空"
    print(f"✓ 获取 {len(result)} 条数据耗时: {elapsed:.2f}秒")
    print(f"  平均速度: {len(result)/elapsed:.0f} 条/秒")


@pytest.mark.integration
def test_get_price_data_quality():
    """测试数据质量"""
    provider = _get_provider()
    
    result = provider.get_price(
        TEST_STOCKS["平安银行"],
        start_date="2024-01-01",
        end_date="2024-12-31",
        frequency="daily",
        fq="none",
    )
    
    assert not result.empty, "数据为空"
    
    # 检查数据质量
    assert not result["close"].isna().any(), "收盘价存在 NaN"
    assert (result["close"] > 0).all(), "收盘价应该大于 0"
    assert (result["volume"] >= 0).all(), "成交量应该大于等于 0"
    
    # 检查 OHLC 逻辑
    assert (result["high"] >= result["low"]).all(), "最高价应该 >= 最低价"
    assert (result["high"] >= result["close"]).all(), "最高价应该 >= 收盘价"
    assert (result["low"] <= result["close"]).all(), "最低价应该 <= 收盘价"
    
    print(f"✓ 数据质量检查通过")
    print(f"  数据条数: {len(result)}")
    print(f"  日期范围: {result.index[0]} ~ {result.index[-1]}")
    print(f"  价格范围: {result['close'].min():.2f} ~ {result['close'].max():.2f}")
