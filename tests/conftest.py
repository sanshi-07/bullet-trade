"""
Pytest 全局配置与命令行参数（tests 作用域）。

新增参数：
- --live-providers=miniqmt 用于在线用例的 Provider 指定（默认 miniqmt）。
- 兼容旧用法：--requires-network（等价于 -m 过滤），便于脚本沿用。

示例：
- 只跑联网用例并指定 miniqmt：
  pytest -q -m requires_network bullet-trade/tests/unit/test_exec_and_dividends_reference.py --live-providers=miniqmt
- 旧用法等价：
  pytest -q --requires-network bullet-trade/tests/unit/test_exec_and_dividends_reference.py --live-providers=miniqmt
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-providers",
        action="store",
        default="miniqmt",
        help="Comma separated provider list for online tests (e.g. miniqmt)",
    )
    parser.addoption(
        "--requires-network",
        action="store_true",
        default=False,
        help="Compatibility: filter tests to requires_network",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "provider_name" in metafunc.fixturenames:
        opt = metafunc.config.getoption("--live-providers") or "miniqmt"
        providers = [p.strip() for p in str(opt).split(",") if p.strip()]
        metafunc.parametrize("provider_name", providers, scope="session")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """默认不运行联网用例；仅在用户显式请求时才纳入执行。"""
    marker_expr = str(config.getoption("-m") or "")
    want_network = ("requires_network" in marker_expr) or bool(config.getoption("--requires-network"))

    deselected: list[pytest.Item] = []
    kept: list[pytest.Item] = []

    for item in items:
        marks = {m.name for m in item.iter_markers()}
        is_net = "requires_network" in marks

        if is_net:
            if want_network:
                kept.append(item)
            else:
                deselected.append(item)
        else:
            kept.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = kept


@pytest.fixture(autouse=True)
def _reset_core_state():
    """
    为每个用例重置核心全局状态，避免相互污染。
    """
    from bullet_trade.core.globals import reset_globals
    from bullet_trade.core.orders import clear_order_queue
    from bullet_trade.core.runtime import set_current_engine
    from bullet_trade.core.settings import reset_settings
    from bullet_trade.data import api as data_api

    reset_globals()
    reset_settings()
    clear_order_queue()
    set_current_engine(None)
    try:
        data_api.set_current_context(None)
    except Exception:
        pass

    yield

    clear_order_queue()
    set_current_engine(None)
    try:
        data_api.set_current_context(None)
    except Exception:
        pass
