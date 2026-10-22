"""Small MySQL access layer for the future FastAPI service."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import MySQLConnection

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class DatabaseConfigurationError(RuntimeError):
    """Raised when required database configuration is absent."""


def database_config() -> dict[str, Any]:
    required = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT", "3306"),
        "database": os.getenv("DB_NAME", "offline_notes_companion"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }
    missing = [name for name in ("host", "user", "password") if not required[name]]
    if missing:
        raise DatabaseConfigurationError(
            "Missing database environment variables: " + ", ".join(f"DB_{name.upper()}" for name in missing)
        )
    required["port"] = int(required["port"])
    return required


@contextmanager
def get_connection() -> Iterator[MySQLConnection]:
    connection = mysql.connector.connect(**database_config())
    try:
        yield connection
    finally:
        connection.close()


def execute(
    statement: str,
    parameters: tuple[Any, ...] = (),
    *,
    fetch: bool = False,
) -> list[tuple[Any, ...]] | int:
    """Execute one parameterized statement and commit it."""
    with get_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall() if fetch else cursor.rowcount
            connection.commit()
            return rows
        finally:
            cursor.close()
