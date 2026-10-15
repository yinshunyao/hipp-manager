"""SQLAlchemy 引擎 + 建表；业务用原生 SQL。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS user (
  user_id VARCHAR(36) PRIMARY KEY,
  phone VARCHAR(20) NOT NULL UNIQUE,
  nickname VARCHAR(64) NOT NULL DEFAULT '',
  password_hash VARCHAR(255) NOT NULL DEFAULT '',
  has_password INTEGER NOT NULL DEFAULT 0,
  avatar_path VARCHAR(512) NOT NULL DEFAULT '',
  balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
  created_at VARCHAR(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS recharge_preset (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  amount INTEGER NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS recharge_order (
  order_id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  amount NUMERIC(10, 2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at VARCHAR(32) NOT NULL,
  paid_at VARCHAR(32),
  payment_channel VARCHAR(20) NOT NULL DEFAULT '',
  payment_order_id VARCHAR(100) NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS billing_transaction (
  tx_id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  type VARCHAR(20) NOT NULL,
  amount NUMERIC(10, 2) NOT NULL,
  product VARCHAR(20) NOT NULL,
  balance_after NUMERIC(12, 2) NOT NULL,
  ref_id VARCHAR(64) NOT NULL DEFAULT '',
  remark VARCHAR(500) NOT NULL DEFAULT '',
  payment_channel VARCHAR(20) NOT NULL DEFAULT '',
  payment_order_id VARCHAR(100) NOT NULL DEFAULT '',
  created_at VARCHAR(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS user_monthly_consumption (
  user_id VARCHAR(36) NOT NULL,
  bill_month VARCHAR(7) NOT NULL,
  confirmed_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
  updated_at VARCHAR(32) NOT NULL,
  PRIMARY KEY (user_id, bill_month)
);
CREATE INDEX IF NOT EXISTS idx_tx_user_created ON billing_transaction(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_recharge_user ON recharge_order(user_id, created_at);
"""

_SCHEMA_MYSQL = """
CREATE TABLE IF NOT EXISTS user (
  user_id VARCHAR(36) PRIMARY KEY,
  phone VARCHAR(20) NOT NULL UNIQUE,
  nickname VARCHAR(64) NOT NULL DEFAULT '',
  password_hash VARCHAR(255) NOT NULL DEFAULT '',
  has_password TINYINT NOT NULL DEFAULT 0,
  avatar_path VARCHAR(512) NOT NULL DEFAULT '',
  balance DECIMAL(12, 2) NOT NULL DEFAULT 0,
  created_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS recharge_preset (
  id INT AUTO_INCREMENT PRIMARY KEY,
  amount INT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS recharge_order (
  order_id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  amount DECIMAL(10, 2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at VARCHAR(32) NOT NULL,
  paid_at VARCHAR(32) NULL,
  payment_channel VARCHAR(20) NOT NULL DEFAULT '',
  payment_order_id VARCHAR(100) NOT NULL DEFAULT '',
  KEY idx_recharge_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS billing_transaction (
  tx_id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  type VARCHAR(20) NOT NULL,
  amount DECIMAL(10, 2) NOT NULL,
  product VARCHAR(20) NOT NULL,
  balance_after DECIMAL(12, 2) NOT NULL,
  ref_id VARCHAR(64) NOT NULL DEFAULT '',
  remark VARCHAR(500) NOT NULL DEFAULT '',
  payment_channel VARCHAR(20) NOT NULL DEFAULT '',
  payment_order_id VARCHAR(100) NOT NULL DEFAULT '',
  created_at VARCHAR(32) NOT NULL,
  KEY idx_tx_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_monthly_consumption (
  user_id VARCHAR(36) NOT NULL,
  bill_month VARCHAR(7) NOT NULL,
  confirmed_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
  updated_at VARCHAR(32) NOT NULL,
  PRIMARY KEY (user_id, bill_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def make_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)


def init_schema(engine: Engine) -> None:
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    ddl = _SCHEMA_SQLITE if is_sqlite else _SCHEMA_MYSQL
    with engine.begin() as conn:
        for stmt in ddl.split(";"):
            piece = stmt.strip()
            if piece:
                conn.execute(text(piece))
        if not is_sqlite:
            _ensure_mysql_column_widths(conn)
        _seed_presets(conn)


def _ensure_mysql_column_widths(conn: Connection) -> None:
    """已建库时加宽口令/头像列（幂等）。"""
    conn.execute(text("ALTER TABLE user MODIFY password_hash VARCHAR(255) NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE user MODIFY avatar_path VARCHAR(512) NOT NULL DEFAULT ''"))


def _seed_presets(conn: Connection) -> None:
    row = conn.execute(text("SELECT COUNT(*) FROM recharge_preset")).fetchone()
    if row and int(row[0]) > 0:
        return
    for amount, order in ((10, 1), (50, 2), (100, 3), (200, 4), (500, 5)):
        conn.execute(
            text(
                "INSERT INTO recharge_preset (amount, sort_order, enabled) VALUES (:a, :o, 1)"
            ),
            {"a": amount, "o": order},
        )


@contextmanager
def connect(engine: Engine) -> Iterator[Connection]:
    with engine.begin() as conn:
        yield conn
