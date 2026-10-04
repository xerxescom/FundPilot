"""调度器：启用后每天在 sync_nav_cron 创建一个“更新今日数据”批次。

批次由独立 worker 进程消费（python -m app.worker），步骤按依赖推进，
不再使用固定分钟偏移。旧的 app/jobs/*_job.py 包装保留可导入以兼容脚本与测试，
但不再注册到调度器。
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.jobs.daily_update_job import enqueue_daily_update_batch


def create_scheduler() -> BackgroundScheduler:
    sync_hour, sync_minute = (int(part) for part in get_settings().sync_nav_cron.split(":", 1))
    scheduler = BackgroundScheduler(timezone="Asia/Hong_Kong")
    scheduler.add_job(
        enqueue_daily_update_batch,
        "cron",
        hour=sync_hour,
        minute=sync_minute,
        id="daily_update",
        # 进程宕机恢复后 1 小时内的错过任务仍会补跑；多次 misfire 合并为一次
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
