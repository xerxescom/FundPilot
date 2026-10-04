"""独立批次 worker 进程。

本地运行：
    python -m app.worker              # 常驻轮询
    python -m app.worker --once       # 只处理一个步骤项（调试/CI）
    python -m app.worker --healthcheck  # 容器探针：只检查数据库连通性
Docker Compose 中作为独立服务运行同一条命令。
"""

from __future__ import annotations

import argparse
import signal
import threading

from loguru import logger
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, init_db
from app.services.batch_worker_service import run_forever, run_once, worker_id


def main() -> int:
    parser = argparse.ArgumentParser(description="FundPilot 批次 worker")
    parser.add_argument("--once", action="store_true", help="只处理一个步骤项后退出")
    parser.add_argument("--worker-id", default=None, help="自定义 worker 标识（默认 host:pid:uuid）")
    parser.add_argument(
        "--healthcheck", action="store_true", help="只检查数据库连通性后退出（供容器探针使用）"
    )
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    init_db()

    if args.healthcheck:
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - 探针只关心成败
            logger.error(f"健康检查失败：{exc}")
            return 1
        return 0

    if settings.worker_metrics_port:
        from prometheus_client import start_http_server

        start_http_server(settings.worker_metrics_port)
        logger.info(f"worker 指标已在端口 {settings.worker_metrics_port} 暴露")

    owner = args.worker_id or worker_id()

    if args.once:
        with SessionLocal() as db:
            did_work = run_once(db, owner)
        logger.info(f"--once 完成：{'执行了一个步骤项' if did_work else '当前没有待处理项'}")
        return 0

    stop_event = threading.Event()

    def _request_stop(signum, frame):  # noqa: ARG001 - signal handler signature
        logger.info(f"收到信号 {signum}，等待当前步骤结束后退出")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _request_stop)
        except (ValueError, OSError):  # 某些平台不支持 SIGTERM
            continue

    run_forever(stop_event, owner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
