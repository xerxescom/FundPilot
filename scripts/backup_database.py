"""备份 PostgreSQL 数据库（pg_dump custom 格式），输出文件大小与 SHA256。

默认通过 Docker 容器执行 pg_dump（与 docker-compose 部署一致）；
本机装有 pg_dump 时可用 --local 直接调用。

Run:
    python scripts/backup_database.py
    python scripts/backup_database.py --container fundpilot_postgres --database fund_watcher --out-dir backups
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings

DEFAULT_CONTAINER = "fundpilot_postgres"


def _parse_args() -> argparse.Namespace:
    settings = get_settings()
    url = make_url(settings.database_url)
    parser = argparse.ArgumentParser(description="备份 FundPilot 数据库")
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help="PostgreSQL 容器名")
    parser.add_argument("--database", default=url.database or "fund_watcher", help="数据库名")
    parser.add_argument("--user", default=url.username or "postgres", help="数据库用户")
    parser.add_argument("--out-dir", default="backups", help="备份输出目录")
    parser.add_argument("--local", action="store_true", help="使用本机 pg_dump 而不是 Docker")
    return parser.parse_args()


def _container_running(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"{args.database}_{stamp}.dump"

    if args.local:
        if shutil.which("pg_dump") is None:
            print("本机未找到 pg_dump，请去掉 --local 使用 Docker 备份。")
            return 2
        command = ["pg_dump", "-Fc", "-U", args.user, "-d", args.database, "-f", str(target)]
    else:
        if not _container_running(args.container):
            print(f"容器 {args.container} 未运行；请先 docker compose up -d postgres，或改用 --local。")
            return 2
        command = ["docker", "exec", args.container, "pg_dump", "-Fc", "-U", args.user, "-d", args.database]

    print(f"备份 {args.database} → {target}")
    if args.local:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"备份失败：{result.stderr.strip()}")
            return 1
    else:
        with target.open("wb") as handle:
            result = subprocess.run(command, stdout=handle)
        if result.returncode != 0:
            target.unlink(missing_ok=True)
            print("备份失败：pg_dump 返回非零退出码")
            return 1

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"完成：{target.name}（{size_mb:.2f} MB）")
    print(f"SHA256：{_sha256(target)}")
    print("提示：升级/恢复演练前请保留该文件，并用 restore_database.py 恢复到独立测试库核对。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
