from pathlib import Path

from scripts.backup_database import prune_backups


def _make_dump(out_dir: Path, name: str) -> Path:
    path = out_dir / name
    path.write_bytes(b"dump")
    return path


def test_prune_backups_keeps_newest_by_timestamp_name(tmp_path):
    for stamp in ("20260101T030000Z", "20260102T030000Z", "20260103T030000Z", "20260104T030000Z"):
        _make_dump(tmp_path, f"fund_watcher_{stamp}.dump")

    removed = prune_backups(tmp_path, "fund_watcher", keep=2)

    assert [path.name for path in removed] == [
        "fund_watcher_20260101T030000Z.dump",
        "fund_watcher_20260102T030000Z.dump",
    ]
    remaining = sorted(path.name for path in tmp_path.glob("fund_watcher_*.dump"))
    assert remaining == [
        "fund_watcher_20260103T030000Z.dump",
        "fund_watcher_20260104T030000Z.dump",
    ]


def test_prune_backups_keep_zero_keeps_everything(tmp_path):
    _make_dump(tmp_path, "fund_watcher_20260101T030000Z.dump")
    _make_dump(tmp_path, "fund_watcher_20260102T030000Z.dump")

    assert prune_backups(tmp_path, "fund_watcher", keep=0) == []
    assert len(list(tmp_path.glob("fund_watcher_*.dump"))) == 2


def test_prune_backups_ignores_other_databases(tmp_path):
    _make_dump(tmp_path, "fund_watcher_20260101T030000Z.dump")
    _make_dump(tmp_path, "fund_watcher_20260102T030000Z.dump")
    _make_dump(tmp_path, "other_db_20250101T030000Z.dump")

    removed = prune_backups(tmp_path, "fund_watcher", keep=1)

    assert [path.name for path in removed] == ["fund_watcher_20260101T030000Z.dump"]
    assert (tmp_path / "other_db_20250101T030000Z.dump").exists()


def test_prune_backups_noop_when_under_limit(tmp_path):
    _make_dump(tmp_path, "fund_watcher_20260101T030000Z.dump")

    assert prune_backups(tmp_path, "fund_watcher", keep=5) == []
