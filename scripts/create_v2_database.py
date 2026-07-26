"""명시적으로 확인한 빈 v2 DB에 canonical Alembic migration을 적용한다."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

import pymysql

from realty_radar.config import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="realty_radar_v2")
    parser.add_argument("--confirm-create", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.database) or args.confirm_create != args.database:
        raise SystemExit("--confirm-create must exactly match a safe --database name")

    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{args.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    finally:
        connection.close()

    environment = os.environ.copy()
    environment["MYSQL_DATABASE"] = args.database
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=environment)


if __name__ == "__main__":
    main()
