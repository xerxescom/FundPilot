"""每日更新批次：步骤依赖图、资产范围展开、幂等创建、状态聚合与重试。

批次是“更新今日数据”的唯一入口：同一交易日按 idempotency_key 唯一，
重复点击返回同一批次；状态由子项聚合，pending（暂未发布）不计入失败。
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AssetInfo, FundInfo, PortfolioPosition, TaskBatch, TaskBatchItem, Watchlist
from app.services import asset_service, trading_calendar_service

BATCH_TYPE_DAILY = "daily_update"

STEP_ORDER = ("market", "sync_nav", "quality_check", "calc_indicators", "calc_scores", "alerts", "report")
GLOBAL_STEPS = ("market", "alerts", "report")
FUND_STEPS = ("sync_nav", "quality_check", "calc_indicators", "calc_scores")
LISTED_STEPS = ("sync_nav", "quality_check")
STEP_LABELS = {
    "market": "行情及市场背景",
    "sync_nav": "同步行情",
    "quality_check": "数据质量检查",
    "calc_indicators": "计算指标",
    "calc_scores": "生成评分",
    "alerts": "风险预警",
    "report": "生成报告",
}
# 步骤依赖：(依赖步骤, 是否硬依赖)。硬依赖失败/暂未发布会阻断同资产下游；
# alerts 是对全部资产项的软依赖，在 dependency_state 中单独处理。
STEP_DEPS: dict[str, tuple[tuple[str, bool], ...]] = {
    "market": (),
    "sync_nav": (("market", False),),
    "quality_check": (("sync_nav", True),),
    "calc_indicators": (("quality_check", True),),
    "calc_scores": (("calc_indicators", True),),
    "alerts": (),
    "report": (("alerts", False),),
}

ITEM_QUEUED = "queued"
ITEM_RUNNING = "running"
ITEM_SUCCESS = "success"
ITEM_FAILED = "failed"
ITEM_SKIPPED = "skipped"
ITEM_PENDING = "pending"
ITEM_INTERRUPTED = "interrupted"
ITEM_TERMINAL = {ITEM_SUCCESS, ITEM_FAILED, ITEM_SKIPPED, ITEM_PENDING, ITEM_INTERRUPTED}
ITEM_ACTIVE = {ITEM_QUEUED, ITEM_RUNNING}
RETRYABLE_STATUSES = {ITEM_FAILED, ITEM_INTERRUPTED, ITEM_PENDING}

BATCH_QUEUED = "queued"
BATCH_RUNNING = "running"
BATCH_SUCCESS = "success"
BATCH_PARTIAL_SUCCESS = "partial_success"
BATCH_FAILED = "failed"
BATCH_INTERRUPTED = "interrupted"


def steps_for(asset_type: str) -> tuple[str, ...]:
    return FUND_STEPS if asset_type == "fund" else LISTED_STEPS


def expand_universe(db: Session) -> list[dict]:
    """自选基金 ∪ 持仓基金/股票/ETF，按资产去重并带显示名。"""
    funds: dict[str, str | None] = {}
    for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))):
        funds[asset_service.normalize_asset_code(item.fund_code, "fund")] = item.fund_name

    listed: dict[tuple[str, str], str | None] = {}
    for position in db.scalars(select(PortfolioPosition)):
        asset_type = position.asset_type or "fund"
        raw_code = position.asset_code or position.fund_code
        if not raw_code:
            continue
        code = asset_service.normalize_asset_code(raw_code, asset_type)
        if asset_type == "fund":
            funds.setdefault(code, None)
        elif asset_type in asset_service.LISTED_ASSET_TYPES:
            listed.setdefault((asset_type, code), None)

    fund_names: dict[str, str] = {}
    if funds:
        fund_names = {
            item.fund_code: item.fund_name
            for item in db.scalars(select(FundInfo).where(FundInfo.fund_code.in_(list(funds))))
            if item.fund_name
        }
    asset_names: dict[str, str] = {}
    listed_codes = [code for _, code in listed]
    if listed_codes:
        asset_names = {
            item.asset_code: item.asset_name
            for item in db.scalars(select(AssetInfo).where(AssetInfo.asset_code.in_(listed_codes)))
        }

    universe: list[dict] = []
    for code, watchlist_name in sorted(funds.items()):
        universe.append(
            {"asset_type": "fund", "asset_code": code, "display_name": watchlist_name or fund_names.get(code)}
        )
    for asset_type, code in sorted(listed):
        universe.append({"asset_type": asset_type, "asset_code": code, "display_name": asset_names.get(code)})
    return universe


def _create_items(db: Session, batch: TaskBatch) -> list[TaskBatchItem]:
    settings = get_settings()
    universe = expand_universe(db)
    items: list[TaskBatchItem] = []
    for asset in universe:
        for step in steps_for(asset["asset_type"]):
            items.append(
                TaskBatchItem(
                    batch_id=batch.id,
                    step=step,
                    asset_type=asset["asset_type"],
                    asset_code=asset["asset_code"],
                    display_name=asset["display_name"],
                    status=ITEM_QUEUED,
                    max_retries=settings.batch_item_max_retries,
                    idempotency_key=f"{batch.idempotency_key}:{step}:{asset['asset_type']}:{asset['asset_code']}",
                )
            )
    for step in GLOBAL_STEPS:
        items.append(
            TaskBatchItem(
                batch_id=batch.id,
                step=step,
                asset_type="",
                asset_code="",
                display_name=STEP_LABELS[step],
                status=ITEM_QUEUED,
                max_retries=settings.batch_item_max_retries,
                idempotency_key=f"{batch.idempotency_key}:{step}::",
            )
        )
    db.add_all(items)
    db.flush()
    params = dict(batch.params_json or {})
    params["universe"] = {
        "funds": sum(1 for asset in universe if asset["asset_type"] == "fund"),
        "stocks": sum(1 for asset in universe if asset["asset_type"] == "stock"),
        "etfs": sum(1 for asset in universe if asset["asset_type"] == "etf"),
    }
    batch.params_json = params
    return items


def derive_batch_status(statuses: list[str]) -> str:
    if ITEM_RUNNING in statuses:
        return BATCH_RUNNING
    if ITEM_QUEUED in statuses:
        return BATCH_QUEUED
    if ITEM_INTERRUPTED in statuses:
        return BATCH_INTERRUPTED  # 可恢复，优先于失败展示
    failures = statuses.count(ITEM_FAILED)
    successes = statuses.count(ITEM_SUCCESS)
    others = statuses.count(ITEM_SKIPPED) + statuses.count(ITEM_PENDING)
    if failures and (successes or others):
        return BATCH_PARTIAL_SUCCESS
    if failures:
        return BATCH_FAILED
    return BATCH_SUCCESS


def build_coverage(db: Session, batch: TaskBatch, items: list[TaskBatchItem]) -> dict:
    per_step: dict[str, dict[str, int]] = {}
    for item in items:
        per_step.setdefault(item.step, Counter())[item.status] += 1
    sync_items = [item for item in items if item.step == "sync_nav"]
    pending = [item for item in sync_items if item.status == ITEM_PENDING]
    failed = [item for item in sync_items if item.status == ITEM_FAILED]
    notes: list[str] = []
    if pending:
        names = "、".join((item.display_name or item.asset_code) for item in pending[:5])
        notes.append(f"{len(pending)} 个资产暂未发布 {batch.trade_date} 数据（{names}），沿用最近可用数据")
    if failed:
        names = "、".join((item.display_name or item.asset_code) for item in failed[:5])
        notes.append(f"{len(failed)} 个资产行情同步失败（{names}）")
    params = batch.params_json or {}
    return {
        "trade_date": batch.trade_date.isoformat() if batch.trade_date else None,
        "calendar_source": params.get("calendar_source"),
        "steps": {step: dict(counts) for step, counts in per_step.items()},
        "asset_counts": {
            "total": len(sync_items),
            "success": sum(1 for item in sync_items if item.status == ITEM_SUCCESS),
            "pending": len(pending),
            "failed": len(failed),
        },
        "notes": notes,
    }


def refresh_batch_status(db: Session, batch: TaskBatch) -> TaskBatch:
    items = list(db.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)))
    statuses = [item.status for item in items]
    batch.total_count = len(items)
    batch.success_count = statuses.count(ITEM_SUCCESS)
    batch.failure_count = statuses.count(ITEM_FAILED)
    batch.skipped_count = statuses.count(ITEM_SKIPPED)
    batch.pending_count = statuses.count(ITEM_PENDING)
    batch.interrupted_count = statuses.count(ITEM_INTERRUPTED)
    batch.status = derive_batch_status(statuses)
    now = datetime.now()
    if any(status in ITEM_ACTIVE for status in statuses):
        batch.started_at = batch.started_at or now
        batch.finished_at = None
    elif all(status in ITEM_TERMINAL for status in statuses):
        batch.finished_at = batch.finished_at or now
        batch.lease_owner = None
        batch.lease_expires_at = None
    batch.coverage_json = build_coverage(db, batch, items)
    db.flush()
    return batch


def get_item(
    db: Session, batch: TaskBatch, step: str, asset_type: str, asset_code: str
) -> TaskBatchItem | None:
    return db.scalar(
        select(TaskBatchItem).where(
            TaskBatchItem.batch_id == batch.id,
            TaskBatchItem.step == step,
            TaskBatchItem.asset_type == asset_type,
            TaskBatchItem.asset_code == asset_code,
        )
    )


def blocking_dependency(db: Session, batch: TaskBatch, item: TaskBatchItem) -> tuple[str, TaskBatchItem] | None:
    """返回第一个阻断该硬依赖的 (依赖步骤, 依赖项)；无阻断返回 None。"""
    for dep_step, hard in STEP_DEPS.get(item.step, ()):
        if not hard:
            continue
        dep = get_item(db, batch, dep_step, item.asset_type, item.asset_code)
        if dep is None:
            continue
        if dep.status in {ITEM_FAILED, ITEM_INTERRUPTED, ITEM_PENDING, ITEM_SKIPPED}:
            return dep_step, dep
    return None


def item_dependency_state(db: Session, batch: TaskBatch, item: TaskBatchItem) -> str:
    """ready / waiting / blocked_failed / blocked_pending / blocked_skipped。"""
    if item.step == "alerts":
        asset_items = list(
            db.scalars(
                select(TaskBatchItem).where(
                    TaskBatchItem.batch_id == batch.id, TaskBatchItem.asset_code != ""
                )
            )
        )
        if any(other.status in ITEM_ACTIVE for other in asset_items):
            return "waiting"
        return "ready"
    for dep_step, hard in STEP_DEPS.get(item.step, ()):
        dep = get_item(db, batch, dep_step, item.asset_type, item.asset_code)
        if dep is None:
            continue
        if dep.status in ITEM_ACTIVE:
            return "waiting"
        if not hard:
            continue
        if dep.status in {ITEM_FAILED, ITEM_INTERRUPTED}:
            return "blocked_failed"
        if dep.status == ITEM_PENDING:
            return "blocked_pending"
        if dep.status == ITEM_SKIPPED:
            return "blocked_skipped"
    return "ready"


def create_or_get_daily_batch(
    db: Session, trade_date: date | None = None, now: datetime | None = None, trigger: str = "api"
) -> tuple[TaskBatch, bool]:
    """创建或取得当日批次；重复调用返回同一批次（created=False）。"""
    now = now or datetime.now()
    trade_date = trade_date or trading_calendar_service.latest_expected_trade_date(db, now)
    key = f"{BATCH_TYPE_DAILY}:{trade_date.isoformat()}"
    existing = db.scalar(select(TaskBatch).where(TaskBatch.idempotency_key == key))
    if existing is not None:
        return _rearm_for_repeat_click(db, existing), False

    batch = TaskBatch(
        batch_type=BATCH_TYPE_DAILY,
        idempotency_key=key,
        status=BATCH_QUEUED,
        trade_date=trade_date,
        params_json={
            "trigger": trigger,
            "trade_date": trade_date.isoformat(),
            "calendar_source": trading_calendar_service.calendar_source_for(db, trade_date),
        },
        total_count=0,
        success_count=0,
        failure_count=0,
        skipped_count=0,
        pending_count=0,
        interrupted_count=0,
    )
    db.add(batch)
    try:
        db.flush()
        _create_items(db, batch)
        refresh_batch_status(db, batch)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(TaskBatch).where(TaskBatch.idempotency_key == key))
        if existing is None:
            raise
        return existing, False
    db.commit()
    db.refresh(batch)
    return batch, True


def _reset_item(item: TaskBatchItem, count_retry: bool = True) -> None:
    item.status = ITEM_QUEUED
    if count_retry:
        item.retry_count += 1
    item.error_class = None
    item.error_message = None
    item.lease_owner = None
    item.lease_expires_at = None
    item.result_json = None


def _blocked_by_key(item: TaskBatchItem) -> tuple[str, str, str] | None:
    blocked = (item.result_json or {}).get("blocked_by") if item.result_json else None
    if not isinstance(blocked, dict) or not blocked.get("step"):
        return None
    return (str(blocked["step"]), item.asset_type, item.asset_code)


def _rearm_items(db: Session, batch: TaskBatch, items: list[TaskBatchItem]) -> int:
    """把待重跑项（含被它们阻断的下游跳过项）重新排入队列。"""
    if not items:
        return 0
    keys = {(item.step, item.asset_type, item.asset_code) for item in items}
    count = 0
    for item in items:
        _reset_item(item, count_retry=item.status in {ITEM_FAILED, ITEM_INTERRUPTED})
        count += 1
    all_items = list(db.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)))
    for item in all_items:
        if item.status != ITEM_SKIPPED or item in items:
            continue
        if _blocked_by_key(item) in keys:
            _reset_item(item, count_retry=False)
            count += 1
    db.flush()
    return count


def _rearm_for_repeat_click(db: Session, batch: TaskBatch) -> TaskBatch:
    """终态批次再次点击时，补跑暂未发布/可恢复中断的项。"""
    if batch.status in {BATCH_QUEUED, BATCH_RUNNING}:
        return batch
    items = list(db.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)))
    candidates = [
        item
        for item in items
        if item.status == ITEM_PENDING
        or (item.status == ITEM_INTERRUPTED and item.retry_count < item.max_retries)
    ]
    if not candidates:
        return batch
    _rearm_items(db, batch, candidates)
    refresh_batch_status(db, batch)
    db.commit()
    return batch


def retry_batch_items(
    db: Session,
    batch_id: int,
    step: str | None = None,
    asset_type: str | None = None,
    asset_code: str | None = None,
    include_global: bool = False,
) -> tuple[TaskBatch | None, int]:
    """手动重试失败/中断/暂未发布的项；默认不含全局步骤（报告与批次绑定）。"""
    batch = db.get(TaskBatch, batch_id)
    if batch is None:
        return None, 0
    items = list(db.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)))
    targets = [item for item in items if item.status in RETRYABLE_STATUSES]
    if step:
        targets = [item for item in targets if item.step == step]
    if asset_type:
        targets = [item for item in targets if item.asset_type == asset_type]
    if asset_code:
        targets = [item for item in targets if item.asset_code == asset_code]
    if not include_global:
        targets = [item for item in targets if item.asset_code != ""]
    if not targets:
        return batch, 0
    count = _rearm_items(db, batch, targets)
    refresh_batch_status(db, batch)
    db.commit()
    return batch, count


def list_batches(db: Session, limit: int = 20) -> list[TaskBatch]:
    return list(
        db.scalars(select(TaskBatch).order_by(TaskBatch.created_at.desc(), TaskBatch.id.desc()).limit(limit))
    )


def batch_detail(db: Session, batch: TaskBatch) -> dict:
    items = list(
        db.scalars(
            select(TaskBatchItem)
            .where(TaskBatchItem.batch_id == batch.id)
            .order_by(TaskBatchItem.id.asc())
        )
    )
    # 步骤优先排序，便于按依赖链阅读明细
    items.sort(key=lambda item: (STEP_ORDER.index(item.step), item.asset_type, item.asset_code))
    grouped: dict[str, list[TaskBatchItem]] = {step: [] for step in STEP_ORDER}
    for item in items:
        grouped.setdefault(item.step, []).append(item)
    return {"batch": batch, "items_by_step": grouped, "items": items}
