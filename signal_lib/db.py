import sqlite3
import os
import pandas as pd
from signal_lib.config import DB_PATH, DATA_DIR


def get_conn() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT 'naver',
            stock_name TEXT NOT NULL,
            stock_code TEXT,
            sector TEXT,
            broker TEXT,
            title TEXT,
            target_price INTEGER,
            opinion TEXT,
            report_date DATE,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_name, broker, report_date, title)
        );
        CREATE INDEX IF NOT EXISTS idx_reports_stock_date ON reports(stock_name, report_date);
        CREATE INDEX IF NOT EXISTS idx_reports_sector_date ON reports(sector, report_date);

        CREATE TABLE IF NOT EXISTS consensus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_name TEXT NOT NULL,
            stock_code TEXT,
            consensus_target_price INTEGER,
            num_analysts INTEGER,
            snapshot_date DATE,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_name, snapshot_date)
        );
        CREATE INDEX IF NOT EXISTS idx_consensus_stock_date ON consensus(stock_name, snapshot_date);
    """)
    conn.commit()
    conn.close()


def get_reports(
    start_date: str = None,
    end_date: str = None,
    sectors: list = None,
    stock_name: str = None,
) -> pd.DataFrame:
    conn = get_conn()
    query = "SELECT * FROM reports WHERE 1=1"
    params = []

    if start_date:
        query += " AND report_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND report_date <= ?"
        params.append(end_date)
    if sectors:
        placeholders = ",".join("?" * len(sectors))
        query += f" AND sector IN ({placeholders})"
        params.extend(sectors)
    if stock_name:
        query += " AND stock_name LIKE ?"
        params.append(f"%{stock_name}%")

    query += " ORDER BY report_date DESC"
    df = pd.read_sql_query(query, conn, params=params, parse_dates=["report_date"])
    conn.close()
    return df


def get_consensus(stock_name: str = None) -> pd.DataFrame:
    conn = get_conn()
    query = "SELECT * FROM consensus WHERE 1=1"
    params = []
    if stock_name:
        query += " AND stock_name LIKE ?"
        params.append(f"%{stock_name}%")
    query += " ORDER BY snapshot_date DESC"
    df = pd.read_sql_query(query, conn, params=params, parse_dates=["snapshot_date"])
    conn.close()
    return df


def get_sectors() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT sector FROM reports WHERE sector IS NOT NULL ORDER BY sector").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_stock_names() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT stock_name FROM reports ORDER BY stock_name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_report_count() -> int:
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.close()
    return count
