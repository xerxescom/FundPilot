from apscheduler.schedulers.background import BackgroundScheduler

from app.jobs.ai_report_job import generate_daily_ai_report
from app.jobs.alert_job import generate_risk_alerts
from app.jobs.calc_indicator_job import calc_all_indicators
from app.jobs.market_job import sync_daily_market_context
from app.jobs.score_job import calc_all_scores
from app.jobs.update_nav_job import update_fund_nav


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Hong_Kong")
    scheduler.add_job(update_fund_nav, "cron", hour=18, minute=0, id="update_fund_nav")
    scheduler.add_job(sync_daily_market_context, "cron", hour=18, minute=5, id="sync_market_context")
    scheduler.add_job(calc_all_indicators, "cron", hour=18, minute=10, id="calc_indicators")
    scheduler.add_job(calc_all_scores, "cron", hour=18, minute=20, id="calc_scores")
    scheduler.add_job(generate_daily_ai_report, "cron", hour=18, minute=30, id="daily_ai_report")
    scheduler.add_job(generate_risk_alerts, "cron", hour=18, minute=35, id="risk_alerts")
    return scheduler
