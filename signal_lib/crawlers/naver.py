import re
import sqlite3
from signal_lib.crawlers.base import BaseCrawler
from signal_lib.config import NAVER_RESEARCH_URL
from signal_lib.db import get_conn


class NaverResearchCrawler(BaseCrawler):
    def crawl(self, max_pages: int = 20, progress_callback=None) -> int:
        conn = get_conn()
        total_inserted = 0

        for page in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(page, max_pages)

            try:
                soup = self.fetch(
                    NAVER_RESEARCH_URL,
                    params={"page": page},
                    encoding="euc-kr",
                )
            except Exception as e:
                print(f"[네이버] 페이지 {page} 크롤링 실패: {e}")
                break

            rows = self._parse_list_page(soup)
            if not rows:
                print(f"[네이버] 페이지 {page}: 데이터 없음, 종료")
                break

            for row in rows:
                existing = conn.execute(
                    "SELECT id FROM reports WHERE stock_name=? AND broker=? AND report_date=? AND title=?",
                    (row["stock_name"], row["broker"], row["report_date"], row["title"]),
                ).fetchone()
                if existing:
                    continue

                if row.get("has_pdf"):
                    target_price, opinion = self._fetch_detail(row["detail_nid"])
                else:
                    target_price, opinion = None, None

                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO reports
                           (source, stock_name, stock_code, sector, broker, title, target_price, opinion, report_date, report_url)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            "naver",
                            row["stock_name"],
                            row.get("stock_code"),
                            row["sector"],
                            row["broker"],
                            row["title"],
                            target_price,
                            opinion,
                            row["report_date"],
                            row.get("report_url"),
                        ),
                    )
                    total_inserted += 1
                except sqlite3.Error:
                    pass

            conn.commit()
            print(f"[네이버] 페이지 {page}/{max_pages} 완료 ({len(rows)}건)")

        conn.close()
        return total_inserted

    def _parse_list_page(self, soup) -> list:
        rows = []
        table = soup.find("table", class_="type_1")
        if not table:
            return rows

        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue

            try:
                stock_link = tds[0].find("a")
                if not stock_link:
                    continue
                stock_name = stock_link.get_text(strip=True)

                stock_code = None
                href = stock_link.get("href", "")
                code_match = re.search(r"code=(\d+)", href)
                if code_match:
                    stock_code = code_match.group(1)

                title_tag = tds[1].find("a")
                title = title_tag.get_text(strip=True) if title_tag else ""

                detail_nid = None
                report_url = None
                if title_tag:
                    detail_href = title_tag.get("href", "")
                    nid_match = re.search(r"nid=(\d+)", detail_href)
                    if nid_match:
                        detail_nid = nid_match.group(1)
                        report_url = f"https://finance.naver.com/research/company_read.naver?nid={detail_nid}"

                broker = tds[2].get_text(strip=True)

                has_pdf = bool(tds[3].find("a")) if len(tds) > 3 else False

                report_date_raw = tds[4].get_text(strip=True)
                if "." in report_date_raw:
                    report_date = "20" + report_date_raw if len(report_date_raw) <= 8 else report_date_raw
                    report_date = report_date.replace(".", "-")
                else:
                    report_date = report_date_raw

                sector = None

                rows.append({
                    "stock_name": stock_name,
                    "stock_code": stock_code,
                    "sector": sector,
                    "broker": broker,
                    "title": title,
                    "report_date": report_date,
                    "detail_nid": detail_nid,
                    "report_url": report_url,
                    "has_pdf": has_pdf,
                })
            except (IndexError, ValueError, AttributeError):
                continue

        return rows

    def _fetch_detail(self, nid: str) -> tuple:
        if not nid:
            return None, None

        try:
            soup = self.fetch(
                "https://finance.naver.com/research/company_read.naver",
                params={"nid": nid},
                encoding="euc-kr",
            )

            target_price = None
            opinion = None

            for td in soup.find_all("td"):
                text = td.get_text(strip=True)
                if "목표가" in text and "투자의견" in text:
                    tp_match = re.search(r"목표가([\d,]+)", text)
                    if tp_match:
                        target_price = int(tp_match.group(1).replace(",", ""))

                    op_match = re.search(r"투자의견(\S+)", text)
                    if op_match:
                        opinion = op_match.group(1)
                    break

            return target_price, opinion
        except Exception:
            return None, None


def crawl_naver(max_pages: int = 20, progress_callback=None) -> int:
    crawler = NaverResearchCrawler()
    return crawler.crawl(max_pages=max_pages, progress_callback=progress_callback)


if __name__ == "__main__":
    from db import init_db
    init_db()
    count = crawl_naver(max_pages=3)
    print(f"총 {count}건 수집 완료")
