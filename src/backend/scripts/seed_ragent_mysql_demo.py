"""Seed deterministic RAGENT MySQL demo data."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import asyncmy
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_agent.core.config import settings  # noqa: E402
from scripts.seeders.generators import GENERATORS, ROW_COUNT, TABLES  # noqa: E402


async def connect():
    """按 DA_DB_URL 连接 MySQL。"""
    url = make_url(settings.db_url)
    return await asyncmy.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 3306,
        user=url.username or "root",
        password=url.password or "",
        db=url.database,
        charset=url.query.get("charset", "utf8mb4"),
        autocommit=False,
    )


async def table_counts(conn) -> dict[str, int]:
    """统计所有 demo 表行数。"""
    async with conn.cursor() as cur:
        out = {}
        for table in TABLES:
            await cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            out[table] = int((await cur.fetchone())[0])
        return out


async def table_columns(conn, table: str) -> list[str]:
    """读取 MySQL 真实表列，供 seed 写入时自动对齐。"""
    async with conn.cursor() as cur:
        await cur.execute(f"SHOW COLUMNS FROM `{table}`")
        return [str(row[0]) for row in await cur.fetchall()]


def align_rows(rows: list[dict], columns: list[str]) -> tuple[list[dict], list[str]]:
    """过滤生成器多余字段，并保留有序列名。"""
    column_set = set(columns)
    ordered = [column for column in rows[0].keys() if column in column_set]
    return [{column: row.get(column) for column in ordered} for row in rows], ordered


async def insert_rows(conn, table: str, rows: list[dict], columns: list[str]) -> None:
    """批量插入一张表。"""
    if not rows:
        return
    rows, columns = align_rows(rows, columns)
    if not columns:
        raise RuntimeError(f"{table} has no matching columns for generated rows")
    placeholders = ", ".join(["%s"] * len(columns))
    col_sql = ", ".join(f"`{column}`" for column in columns)
    values = [tuple(row[column] for column in columns) for row in rows]
    async with conn.cursor() as cur:
        await cur.executemany(f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})", values)


async def seed(replace: bool) -> int:
    """执行 demo 数据导入。"""
    conn = await connect()
    try:
        before = await table_counts(conn)
        non_empty = {table: count for table, count in before.items() if count}
        if non_empty and not replace:
            print("Refusing to seed non-empty tables. Run with --replace to reset demo rows.")
            return 2
        async with conn.cursor() as cur:
            if replace:
                for table in TABLES:
                    await cur.execute(f"DELETE FROM `{table}`")
        for table, generator in GENERATORS.items():
            rows = generator()
            if len(rows) != ROW_COUNT:
                raise RuntimeError(f"{table} generated {len(rows)} rows, expected {ROW_COUNT}")
            await insert_rows(conn, table, rows, await table_columns(conn, table))
        await conn.commit()
        for table, count in (await table_counts(conn)).items():
            print(f"{table}\t{count}")
        return 0
    except Exception:
        await conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    """解析命令行并运行 seed。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="delete existing rows before seeding")
    args = parser.parse_args()
    return asyncio.run(seed(args.replace))


if __name__ == "__main__":
    raise SystemExit(main())
