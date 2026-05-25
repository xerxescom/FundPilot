from app.services import task_runner_service
from app.services.task_log_service import latest_task_logs


def test_enqueue_task_records_queued_log(monkeypatch, db_session):
    monkeypatch.setattr(task_runner_service, "_task_factories", lambda db: {"demo": lambda: {"ok": "done"}})

    log = task_runner_service.enqueue_task(db_session, "demo")

    assert log.task_name == "queued_demo"
    assert log.status == "queued"
    assert log.message == "任务已提交后台执行"


def test_run_task_records_failure_count(monkeypatch, db_session):
    monkeypatch.setattr(
        task_runner_service,
        "_task_factories",
        lambda db: {"demo": lambda: {"000001": {"status": "failed"}, "000002": {"status": "success"}}},
    )

    result = task_runner_service.run_task(db_session, "demo")

    assert result["000001"]["status"] == "failed"
    logs = latest_task_logs(db_session)
    assert logs[0].task_name == "manual_demo"
    assert logs[0].failure_count == 1
