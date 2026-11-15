"""Helper de conexao SQLite isolada por servico (Database-per-Service)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def resolve_db_path(env_var: str, default_path: str) -> str:
    """Resolve o caminho do arquivo SQLite a partir da variavel de ambiente do servico."""
    return os.getenv(env_var, default_path)


def get_connection(db_path: str) -> sqlite3.Connection:
    """Abre conexao SQLite com row_factory dict-like no arquivo proprio do servico."""
    path = Path(db_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
