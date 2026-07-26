"""24시간 rollback 기간 후, 백업을 만든 뒤 명시적 legacy table만 DROP한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

import pymysql

from realty_radar.config import settings


LEGACY_TABLES = {
    "crawl_source", "crawl_schedule", "crawl_job", "complex_alias", "apartment_complex", "listing", "listing_history", "listing_snapshot"
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-drop", required=True)
    parser.add_argument("--backup-dir", default="data/backups")
    args = parser.parse_args()
    if args.confirm_drop != args.database:
        raise SystemExit("--confirm-drop must exactly match --database")
    if args.database == settings.mysql_database:
        raise SystemExit("refusing to retire the configured v2 database")

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{args.database}-before-v2-retire-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.sql"
    with backup_path.open("wb") as backup_file:
        subprocess.run(
            ["mysqldump", "--host", settings.mysql_host, "--port", str(settings.mysql_port), "--user", settings.mysql_user, "--databases", args.database],
            check=True,
            stdout=backup_file,
            env={**os.environ, "MYSQL_PWD": settings.mysql_password},
        )

    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=args.database,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (args.database,))
            existing = {row[0] for row in cursor.fetchall()}
            if {"complex_current", "listing_current"} & existing:
                raise SystemExit("refusing to drop a database that contains v2 tables")
            targets = sorted(existing & LEGACY_TABLES)
            if targets:
                cursor.execute("DROP TABLE " + ", ".join(f"`{name}`" for name in targets))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
