"""Prometheus 指标：HTTP 中间件 + 业务计数器 + scrape 时查库的批次仪表盘。

设计要点：
- 私有 Registry + 惰性单例：测试可 ``reset_metrics_for_tests()`` 重建，避免重复注册；
- 指标只反映当前进程：backend 与 worker 各自暴露自己的进程内计数；
- 批次状态用 scrape 时查库的 Gauge，worker 与 backend 共库即可跨进程可见；
- 所有记录函数都吞掉异常——可观测性永远不能影响业务主流程。
"""

from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.core import GaugeMetricFamily

_SKIP_PATHS = {"/metrics", "/health", "/livez", "/readyz"}
_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_UNKNOWN = "unknown"


class MetricsHub:
    """一组进程内指标；与 registry 同生命周期。"""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self.http_requests_total = Counter(
            "fundpilot_http_requests_total",
            "HTTP 请求数",
            ["method", "path", "status"],
            registry=registry,
        )
        self.http_request_duration_seconds = Histogram(
            "fundpilot_http_request_duration_seconds",
            "HTTP 请求耗时（秒）",
            ["method", "path"],
            buckets=_HTTP_BUCKETS,
            registry=registry,
        )
        self.task_runs_total = Counter(
            "fundpilot_task_runs_total", "任务运行次数", ["task_name", "status"], registry=registry
        )
        self.batch_item_outcomes_total = Counter(
            "fundpilot_batch_item_outcomes_total",
            "批次步骤项在本进程内的执行结果",
            ["step", "status"],
            registry=registry,
        )
        self.data_source_requests_total = Counter(
            "fundpilot_data_source_requests_total",
            "数据源请求次数",
            ["source", "operation", "status"],
            registry=registry,
        )


class TaskBatchItemCollector:
    """scrape 时按 (step, status) 聚合 task_batch_item；查库失败不阻断抓取。"""

    def collect(self):
        metric = GaugeMetricFamily(
            "fundpilot_task_batch_items",
            "批次步骤项按状态计数（来自数据库，跨进程）",
            labels=["step", "status"],
        )
        try:
            from sqlalchemy import func, select

            from app.db.models import TaskBatchItem
            from app.db.session import SessionLocal

            with SessionLocal() as db:
                rows = db.execute(
                    select(TaskBatchItem.step, TaskBatchItem.status, func.count())
                    .group_by(TaskBatchItem.step, TaskBatchItem.status)
                ).all()
            for step, status, count in rows:
                metric.add_metric([step or _UNKNOWN, status or _UNKNOWN], count)
        except Exception:  # noqa: BLE001 - 指标失败不能拖垮 /metrics
            pass
        yield metric


_registry: CollectorRegistry | None = None
_hub: MetricsHub | None = None


def get_registry() -> CollectorRegistry:
    global _registry, _hub
    if _registry is None:
        registry = CollectorRegistry()
        _hub = MetricsHub(registry)
        registry.register(TaskBatchItemCollector())
        _registry = registry
    return _registry


def get_hub() -> MetricsHub:
    get_registry()
    assert _hub is not None  # get_registry 保证已创建
    return _hub


def reset_metrics_for_tests() -> None:
    """重建 registry 与 hub；调用方后续必须经 get_hub() 重新获取。"""
    global _registry, _hub
    _registry = None
    _hub = None


def record_task_run(task_name: str, status: str) -> None:
    try:
        get_hub().task_runs_total.labels(
            task_name=task_name or _UNKNOWN, status=status or _UNKNOWN
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def record_batch_item_outcome(step: str, status: str) -> None:
    try:
        get_hub().batch_item_outcomes_total.labels(
            step=step or _UNKNOWN, status=status or _UNKNOWN
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def record_data_source_request(source: str, operation: str, status: str) -> None:
    try:
        get_hub().data_source_requests_total.labels(
            source=source or _UNKNOWN, operation=operation or _UNKNOWN, status=status or _UNKNOWN
        ).inc()
    except Exception:  # noqa: BLE001
        pass


class PrometheusMiddleware:
    """纯 ASGI 中间件：按路由模板记录请求数与耗时，跳过探针与 /metrics 本身。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("path") in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            method = scope.get("method", _UNKNOWN)
            route = scope.get("route")
            path = getattr(route, "path", None) or "unmatched"
            try:
                hub = get_hub()
                hub.http_requests_total.labels(
                    method=method, path=path, status=str(status_holder["status"])
                ).inc()
                hub.http_request_duration_seconds.labels(method=method, path=path).observe(
                    time.perf_counter() - started
                )
            except Exception:  # noqa: BLE001
                pass
