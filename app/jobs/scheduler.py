from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.jobs.ai_report_job import generate_daily_ai_report
from app.jobs.alert_job import generate_risk_alerts
from app.jobs.calc_indicator_job import calc_all_indicators
from app.jobs.market_job import sync_daily_market_context
from app.jobs.score_job import calc_all_scores
from app.jobs.update_nav_job import update_fund_nav


def _cron_time(base_hour: int, base_minute: int, offset_minutes: int) -> tuple[int, int]:
    total_minutes = base_hour * 60 + base_minute + offset_minutes
    total_minutes %= 24 * 60
    return total_minutes // 60, total_minutes % 60


def create_scheduler() -> BackgroundScheduler:
    sync_hour, sync_minute = (int(part) for part in get_settings().sync_nav_cron.split(":", 1))
    scheduler = BackgroundScheduler(timezone="Asia/Hong_Kong")

    # 所有 cron job 共享的健壮性参数：
    #   misfire_grace_time — 进程宕机恢复后，1 小时内的错过任务仍会被补跑
    #   coalesce          — 多次 misfire 合并为一次执行，避免任务堆积
    #   max_instances     — 同一任务同时只允许 1 个实例运行
    _job_defaults = {
        "misfire_grace_time": 3600,
        "coalesce": True,
        "max_instances": 1,
    }

    scheduler.add_job(
        update_fund_nav,
        "cron",
        hour=sync_hour,
        minute=sync_minute,
        id="update_fund_nav",
        **_job_defaults,
    )

    market_hour, market_minute = _cron_time(sync_hour, sync_minute, 5)
    indicator_hour, indicator_minute = _cron_time(sync_hour, sync_minute, 10)
    score_hour, score_minute = _cron_time(sync_hour, sync_minute, 20)
    report_hour, report_minute = _cron_time(sync_hour, sync_minute, 30)
    alert_hour, alert_minute = _cron_time(sync_hour, sync_minute, 35)

    scheduler.add_job(
        sync_daily_market_context,
        "cron",
        hour=market_hour,
        minute=market_minute,
        id="sync_market_context",
        **_job_defaults,
    )
    scheduler.add_job(
        calc_all_indicators,
        "cron",
        hour=indicator_hour,
        minute=indicator_minute,
        id="calc_indicators",
        **_job_defaults,
    )
    scheduler.add_job(
        calc_all_scores,
        "cron",
        hour=score_hour,
        minute=score_minute,
        id="calc_scores",
        **_job_defaults,
    )
    scheduler.add_job(
        generate_daily_ai_report,
        "cron",
        hour=report_hour,
        minute=report_minute,
        id="daily_ai_report",
        **_job_defaults,
    )
    scheduler.add_job(
        generate_risk_alerts,
        "cron",
        hour=alert_hour,
        minute=alert_minute,
        id="risk_alerts",
        **_job_defaults,
    )
    return scheduler

