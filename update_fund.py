import sys
import os
import sqlite3

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fund_lib.apikey import get_dart_key
from fund_lib import dart_client
from shared import gitsync

REPORT_DB = os.path.join(os.path.dirname(__file__), "data", "reports.db")


def progress(i, total):
    print(f"\r  DART 조회 중...  {i}/{total} 종목", end="", flush=True)


def main():
    key = get_dart_key()
    if not key:
        print("  ⚠️ DART API 키가 없습니다. data/dart_key.txt 를 확인하세요.")
        return

    conn = sqlite3.connect(REPORT_DB)
    rows = conn.execute("""
        SELECT stock_name, MAX(stock_code) code, sector
        FROM reports WHERE stock_code IS NOT NULL
        GROUP BY stock_name
    """).fetchall()
    conn.close()
    stocks = [{"stock_name": r[0], "stock_code": r[1], "sector": r[2]} for r in rows]

    print("=" * 50)
    print(f"  기관 지분(5%룰) 수집 시작 — {len(stocks)}개 종목")
    print("  (수 분 소요됩니다)")
    print("=" * 50)

    df = dart_client.collect_holdings(key, stocks, progress_callback=progress)
    dart_client.save_holdings(df)
    print()
    print(f"  {len(df)}건 수집 완료 ({df['stock_name'].nunique()}개 종목)")
    print("-" * 50)

    print("  GitHub에 푸시 중...")
    ok, msg = gitsync.push_data_files(["data/dart_holdings.json"], f"데이터 갱신: 기관 지분 {len(df)}건")
    print(("  ✅ " if ok else "  ℹ️ ") + msg)

    print("=" * 50)
    print("  완료! 1~2분 후 공개 앱에 반영됩니다.")
    print("=" * 50)


if __name__ == "__main__":
    main()
