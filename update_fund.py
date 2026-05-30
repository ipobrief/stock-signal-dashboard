import sys
import os
import sqlite3

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fund_lib.apikey import get_dart_key
from fund_lib import dart_client, loan_client, trade_client
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
    print(f"  기관 지분 {len(df)}건 ({df['stock_name'].nunique()}개 종목)")

    push_files = ["data/dart_holdings.json"]

    # 산업별 대출 (한국은행 ECOS)
    ecos = loan_client.get_ecos_key()
    if ecos:
        print("-" * 50)
        print("  산업별 대출(한국은행) 수집 중...")
        rq, pq = loan_client.latest_quarters(1)
        ld = loan_client.collect_loans(ecos, rq, pq)
        if ld.empty:  # 최근 분기 미확정 시 한 분기 더 과거
            rq, pq = loan_client.latest_quarters(2)
            ld = loan_client.collect_loans(ecos, rq, pq)
        if not ld.empty:
            loan_client.save_loans(ld)
            push_files.append("data/industry_loan.json")
            print(f"  대출 {len(ld)}개 산업 ({pq}->{rq})")

    # 수출입 (관세청)
    dgk = trade_client.get_datagokr_key()
    if dgk:
        print("-" * 50)
        print("  수출입(관세청) 수집 중...")
        import datetime
        today = datetime.date.today()
        recent = (today.replace(day=1) - datetime.timedelta(days=1))      # 전월
        prev = (recent.replace(day=1) - datetime.timedelta(days=1))       # 전전월
        td = trade_client.collect_trade(dgk, recent.strftime("%Y%m"), prev.strftime("%Y%m"),
                                        progress_callback=lambda i, t: print(f"\r    {i}/{t}", end="", flush=True))
        print()
        if not td.empty:
            trade_client.save_trade(td)
            push_files.append("data/customs_trade.json")
            print(f"  수출입 {len(td)}개 품목")
        else:
            print("  (관세청 API 미승인 — 건너뜀)")

    print("-" * 50)
    print("  GitHub에 푸시 중...")
    ok, msg = gitsync.push_data_files(push_files, "데이터 갱신: 산업 자금흐름")
    print(("  ✅ " if ok else "  ℹ️ ") + msg)

    print("=" * 50)
    print("  완료! 1~2분 후 공개 앱에 반영됩니다.")
    print("=" * 50)


if __name__ == "__main__":
    main()
