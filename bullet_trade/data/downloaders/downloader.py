"""
MiniQMT 数据补充模块

仅与 xtquant.xtdata 原生格式交互，不做任何代码转换。

使用方式:
    from bullet_trade.data.providers.cache.downloader import MiniQMTDownloader

    dl = MiniQMTDownloader()

    # 下载A股过去365天日线数据
    dl.download_a_share_history(period="1d", lookback_days=365)

    # 下载板块分类信息
    dl.download_sector_classification()
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd
import logging

logger = logging.getLogger(__name__)


class MiniQMTDownloader:
    """
    基于 xtquant.xtdata 的历史数据下载器。

    纯 xtdata 格式交互，不做聚宽/QMT 代码转换。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.data_dir = self.config.get("data_dir") or os.getenv("QMT_DATA_PATH")

    @staticmethod
    def _ensure_xtdata():
        try:
            from xtquant import xtdata  # type: ignore
            return xtdata
        except ImportError as exc:
            raise ImportError(
                "MiniQMTDownloader 依赖 xtquant，请安装官方 SDK（pip install xtquant）或 bullet-trade[qmt]"
            ) from exc

    @staticmethod
    def _normalize_period(frequency: str) -> str:
        if not frequency:
            return "1d"
        freq = str(frequency).strip().lower()
        alias = {
            "daily": "1d", "day": "1d", "1day": "1d", "d": "1d",
        }
        normalized = alias.get(freq)
        if normalized:
            return normalized
        if freq.endswith(("m", "d")) and freq[:-1].isdigit():
            return freq
        return "1d"

    # ---- A 股行情数据增量下载 ----
    def download_a_share_history(
        self,
        period: str = "1d",
        lookback_days: int = 365,
        end_date: Optional[Union[str, datetime]] = None,
        max_workers: int = 4,
    ) -> Dict[str, Any]:
        """
        增量下载A股历史行情数据，仅下载缺失部分。

        参数:
            period: K 线周期，默认 "1d"
            lookback_days: 回溯天数，默认365
            end_date: 截止日期，默认当天
            max_workers: 并发线程数，默认4

        返回:
            {"total": n, "downloaded": [...], "errors": [...], "stats": {...}}
        """
        xt = self._ensure_xtdata()
        period = self._normalize_period(period)
        end_dt = pd.to_datetime(end_date) if end_date else datetime.now()
        end_str = end_dt.strftime("%Y%m%d")
        start_str = (end_dt - pd.Timedelta(days=lookback_days)).strftime("%Y%m%d")

        # 通过 xtdata 原生获取A股列表
        codes = xt.get_stock_list_in_sector("沪深A股")
        if not codes:
            raise RuntimeError("未获取到沪深A股列表，请检查 xtdata 连接")
        unique_codes = list(dict.fromkeys(codes))

        logger.info(
            "MiniQMT 开始增量下载A股行情数据: %d 只, [%s, %s], period=%s",
            len(unique_codes), start_str, end_str, period,
        )

        result = {
            "total": len(unique_codes),
            "downloaded": [],
            "errors": [],
            "stats": {"start_date": start_str, "end_date": end_str, "period": period},
        }
        counter = {"done": 0}
        lock = threading.Lock()

        def _download_one(code: str) -> None:
            try:
                xt.download_history_data(
                    stock_code=code,
                    period=period,
                    start_time=start_str,
                    end_time=end_str,
                )
                with lock:
                    result["downloaded"].append(code)
                    counter["done"] += 1
                    if counter["done"] % 100 == 0 or counter["done"] == len(unique_codes):
                        logger.info("下载进度: %d/%d", counter["done"], len(unique_codes))
            except Exception as e:
                with lock:
                    result["errors"].append({"code": code, "error": str(e)})
                    counter["done"] += 1
                    if counter["done"] % 100 == 0 or counter["done"] == len(unique_codes):
                        logger.info("下载进度: %d/%d", counter["done"], len(unique_codes))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_download_one, code): code for code in unique_codes}
            for future in as_completed(futures):
                pass

        if result["errors"]:
            logger.warning("下载完成，部分失败: %d 只", len(result["errors"]))
        else:
            logger.info("下载完成: %d 只全部成功", len(result["downloaded"]))
        return result

    # ---- 板块分类信息下载 ----
    def download_sector_classification(self) -> Dict[str, Any]:
        """
        下载并缓存板块分类信息。

        返回:
            {"sectors": {"沪深A股": {"count": n, "codes": [...]}, ...},
             "errors": [...]}
        """
        xt = self._ensure_xtdata()
        result: Dict[str, Any] = {"sectors": {}, "errors": []}

        for sector in ("沪深A股", "沪深ETF", "沪深指数"):
            try:
                codes = xt.get_stock_list_in_sector(sector)
                if codes:
                    result["sectors"][sector] = {"count": len(codes), "codes": codes}
                    logger.info("板块 [%s] 共 %d 只证券", sector, len(codes))
                else:
                    logger.warning("板块 [%s] 返回为空", sector)
            except Exception as e:
                result["errors"].append({"sector": sector, "error": str(e)})
                logger.error("获取板块 [%s] 失败: %s", sector, e)

        if hasattr(xt, "download_index_weight"):
            try:
                xt.download_index_weight()  # type: ignore[attr-defined]
                logger.info("指数权重数据下载请求已发送")
            except Exception as e:
                logger.debug("下载指数权重失败: %s", e)

        return result

    # ---- 指定列表下载（兼容旧用法） ----
    def refresh_data(
        self,
        securities: List[str],
        period: str = "1d",
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        """
        下载指定证券列表的历史行情数据。
        """
        if not securities:
            raise ValueError("refresh_data: securities 不能为空")
        xt = self._ensure_xtdata()
        period = self._normalize_period(period)
        end_str = (
            pd.to_datetime(end_date).strftime("%Y%m%d")
            if end_date
            else datetime.now().strftime("%Y%m%d")
        )
        start_str = (
            pd.to_datetime(start_date).strftime("%Y%m%d")
            if start_date
            else ""
        )
        result: Dict[str, Any] = {"downloaded": [], "errors": []}
        for code in securities:
            try:
                xt.download_history_data(
                    stock_code=code,
                    period=period,
                    start_time=start_str,
                    end_time=end_str,
                )
                result["downloaded"].append(code)
            except Exception as e:
                result["errors"].append({"code": code, "error": str(e)})
        if result["errors"]:
            logger.warning("refresh_data 部分失败: %s", result["errors"])
        return result
