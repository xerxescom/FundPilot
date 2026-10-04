from app.services import task_runner_service
from app.services.task_log_service import derive_task_status, latest_task_logs, summarize_result


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


def test_run_task_reports_partial_success_when_one_of_three_fails(monkeypatch, db_session):
    result = {
        "000001": {"status": "success"},
        "000002": {"status": "success"},
        "000003": {"status": "failed", "quality": {"issues": ["数据源不可用"]}},
    }
    monkeypatch.setattr(task_runner_service, "_task_factories", lambda db: {"demo": lambda: result})

    task_runner_service.run_task(db_session, "demo")

    logs = latest_task_logs(db_session)
    assert logs[0].status == "partial_success"
    assert logs[0].success_count == 2
    assert logs[0].failure_count == 1
    assert logs[0].result_json["000003"]["status"] == "failed"


def test_run_task_reports_failed_when_all_items_fail(monkeypatch, db_session):
    result = {"000001": "failed: 网络错误", "000002": {"status": "failed"}}
    monkeypatch.setattr(task_runner_service, "_task_factories", lambda db: {"demo": lambda: result})

    task_runner_service.run_task(db_session, "demo")

    logs = latest_task_logs(db_session)
    assert logs[0].status == "failed"
    assert logs[0].success_count == 0
    assert logs[0].failure_count == 2


def test_summarize_result_handles_free_form_shapes():
    assert summarize_result({"000001": "failed: 网络错误", "000002": "82.5"}) == (1, 1, 0)
    assert summarize_result({"000001": 12, "000002": "failed: x"}) == (1, 1, 0)
    assert summarize_result({"000001": "skipped", "000002": "ok"}) == (1, 0, 1)
    assert summarize_result({"000001": {"status": "success"}, "000002": {"status": "skipped"}}) == (1, 0, 1)
    assert summarize_result("report-1") == (None, 0, 0)
    assert summarize_result([1, 2, 3]) == (3, 0, 0)


def test_derive_task_status():
    assert derive_task_status(2, 1, 0) == "partial_success"
    assert derive_task_status(0, 1, 1) == "partial_success"
    assert derive_task_status(0, 3, 0) == "failed"
    assert derive_task_status(3, 0, 0) == "success"
    assert derive_task_status(None, 0, 0) == "success"
