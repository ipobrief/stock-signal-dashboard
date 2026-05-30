import sys
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signal_lib.db import init_db, get_report_count
from signal_lib.crawlers.naver import crawl_naver
from shared import gitsync


def progress(page, total):
    print(f"\r  크롤링 중...  {page}/{total} 페이지", end="", flush=True)


def main():
    pages = 200
    if len(sys.argv) > 1:
        try:
            pages = int(sys.argv[1])
        except ValueError:
            pass

    init_db()
    before = get_report_count()

    print("=" * 50)
    print(f"  네이버 리포트 크롤링 시작 ({pages}페이지)")
    print("=" * 50)

    count = crawl_naver(max_pages=pages, progress_callback=progress)
    after = get_report_count()

    print()
    print(f"  신규 {count}건 수집 (총 {before:,} → {after:,}건)")
    print("-" * 50)

    print("  GitHub에 푸시 중...")
    ok, msg = gitsync.push_data(f"데이터 갱신: 리포트 {count}건 신규 수집")
    if ok:
        print(f"  ✅ {msg}")
    else:
        print(f"  ℹ️ {msg}")

    print("=" * 50)
    print("  완료! 1~2분 후 공개 앱에 반영됩니다.")
    print("=" * 50)


if __name__ == "__main__":
    main()
