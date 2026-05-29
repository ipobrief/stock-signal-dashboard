import re
import sqlite3
from datetime import date
from crawlers.base import BaseCrawler
from config import HANKYUNG_CONSENSUS_URL
from db import get_conn


class HankyungConsensusCrawler(BaseCrawler):
    def crawl(self, max_pages: int = 10, progress_callback=None) -> int:
        conn = get_conn()
        total_inserted = 0
        today = date.today().isoformat()

        for page in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(page, max_pages)

            try:
                soup = self.fetch(
                    HANKYUNG_CONSENSUS_URL,
                    params={"sdate": "", "edate": "", "now_page": page},
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[한경] 페이지 {page} 크롤링 실패: {e}")
                break

            rows = self._parse_page(soup, today)
            if not rows:
                print(f"[한경] 페이지 {page}: 데이터 없음, 종료")
                break

            for row in rows:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO consensus
                           (stock_name, stock_code, consensus_target_price, num_analysts, snapshot_date)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            row["stock_name"],
                            row.get("stock_code"),
                            row.get("consensus_target_price"),
                            row.get("num_analysts"),
                            row["snapshot_date"],
                        ),
                    )
                    total_inserted += 1
                except sqlite3.Error:
                    pass

            conn.commit()
            print(f"[한경] 페이지 {page}/{max_pages} 완료 ({len(rows)}건)")

        conn.close()
        return total_inserted

    def _parse_page(self, soup, snapshot_date: str) -> list:
        rows = []
        table = soup.find("table", class_="table_style01") or soup.find("table")
        if not table:
            return rows

        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue

            try:
                stock_link = tds[0].find("a")
                if not stock_link:
                    continue

                stock_name = stock_link.get_text(strip=True)
                stock_code = None
                href = stock_link.get("href", "")
                code_match = re.search(r"code=(\w+)", href)
                if code_match:
                    stock_code = code_match.group(1)

                target_text = tds[1].get_text(strip=True).replace(",", "")
                consensus_target = int(target_text) if target_text.isdigit() else None

                analysts_text = tds[2].get_text(strip=True)
                num_analysts = int(analysts_text) if analysts_text.isdigit() else None

                rows.append({
                    "stock_name": stock_name,
                    "stock_code": stock_code,
                    "consensus_target_price": consensus_target,
                    "num_analysts": num_analysts,
                    "snapshot_date": snapshot_date,
                })
            except (IndexError, ValueError, AttributeError):
                continue

        return rows


def crawl_hankyung(max_pages: int = 10, progress_callback=None) -> int:
    crawler = HankyungConsensusCrawler()
    return crawler.crawl(max_pages=max_pages, progress_callback=progress_callback)


if __name__ == "__main__":
    from db import init_db
    init_db()
    count = crawl_hankyung(max_pages=3)
    print(f"총 {count}건 수집 완료")
