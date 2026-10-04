"""创建当日批次并在当前进程内跑完（开发与演练用）。

正式运行请使用独立 worker 进程：python -m app.worker

Run:
    python scripts/run_daily_batch.py
"""

from app.core.logging import configure_logging
from app.db.session import SessionLocal, init_db
from app.services import batch_worker_service as worker
from app.services import daily_batch_service as batches
from app.services import trading_calendar_service

MAX_STEPS = 500


def main() -> int:
    configure_logging()
    init_db()
    owner = f"{worker.worker_id()}:inline"
    with SessionLocal() as db:
        trading_calendar_service.ensure_calendar_coverage(db)
        batch, created = batches.create_or_get_daily_batch(db, trigger="cli")
        print(f"批次 #{batch.id}（{'新建' if created else '已存在'}），交易日 {batch.trade_date}")
        executed = 0
        while executed < MAX_STEPS and worker.run_once(db, owner):
            executed += 1
        db.refresh(batch)
        print(f"本次执行 {executed} 个步骤项；批次状态：{batch.status}")
        coverage = batch.coverage_json or {}
        for note in coverage.get("notes") or []:
            print(f"覆盖说明：{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
