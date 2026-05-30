import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from sector_lib.config import SECTOR_ETFS, NAVER_SECTOR_URL, USER_AGENT


def get_etf_price(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = "https://fchart.stock.naver.com/siseJson.nhn"
    params = {
        "symbol": code,
        "requestType": "1",
        "startTime": start_date.replace("-", ""),
        "endTime": end_date.replace("-", ""),
        "timeframe": "day",
    }
    try:
        resp = requests.get(url, params=params, timeout=10, headers={"User-Agent": USER_AGENT})
        rows = []
        for match in re.finditer(r'\["(\d{8})",\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)', resp.text):
            date_str, open_p, high, low, close, volume = match.groups()
            rows.append({
                "date": pd.to_datetime(date_str),
                "close": int(close),
                "volume": int(volume),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_all_sector_etf_data(start_date: str, end_date: str) -> dict:
    results = {}
    for sector, info in SECTOR_ETFS.items():
        df = get_etf_price(info["code"], start_date, end_date)
        if not df.empty:
            results[sector] = df
    return results


def get_sector_rankings() -> pd.DataFrame:
    try:
        resp = requests.get(NAVER_SECTOR_URL, headers={"User-Agent": USER_AGENT}, timeout=10)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-kr")

        table = soup.find("table", class_="type_1")
        if not table:
            return pd.DataFrame()

        rows = []
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 5:
                link = tds[0].find("a")
                if not link:
                    continue
                name = link.get_text(strip=True)
                href = link.get("href", "")
                no_match = re.search(r"no=(\d+)", href)
                sector_no = no_match.group(1) if no_match else ""

                change_pct_text = tds[0].find_next_sibling("td") or tds[1]
                texts = [td.get_text(strip=True) for td in tds]

                rows.append({
                    "sector": name,
                    "sector_no": sector_no,
                    "change_pct": texts[1] if len(texts) > 1 else "",
                    "stock_count": texts[2] if len(texts) > 2 else "",
                })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def get_sector_etf_summary(start_date: str, end_date: str) -> pd.DataFrame:
    results = []
    for sector, info in SECTOR_ETFS.items():
        df = get_etf_price(info["code"], start_date, end_date)
        if df.empty or len(df) < 2:
            continue

        first_close = df.iloc[0]["close"]
        last_close = df.iloc[-1]["close"]
        returns_pct = (last_close - first_close) / first_close * 100

        avg_volume = df["volume"].mean()
        recent_volume = df.tail(5)["volume"].mean()
        early_volume = df.head(5)["volume"].mean()
        volume_change = (recent_volume - early_volume) / early_volume * 100 if early_volume > 0 else 0

        avg_value = (df["close"] * df["volume"]).mean()
        recent_value = (df.tail(5)["close"] * df.tail(5)["volume"]).mean()
        early_value = (df.head(5)["close"] * df.head(5)["volume"]).mean()
        value_change = (recent_value - early_value) / early_value * 100 if early_value > 0 else 0

        results.append({
            "sector": sector,
            "etf_name": info["name"],
            "etf_code": info["code"],
            "returns_pct": round(returns_pct, 1),
            "avg_daily_volume": int(avg_volume),
            "volume_change_pct": round(volume_change, 1),
            "avg_daily_value": int(avg_value),
            "value_change_pct": round(value_change, 1),
            "data_points": len(df),
        })

    return pd.DataFrame(results).sort_values("returns_pct", ascending=False) if results else pd.DataFrame()


def get_investor_trading(code: str, pages: int = 3) -> pd.DataFrame:
    rows = []
    for page in range(1, pages + 1):
        try:
            url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}"
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
            soup = BeautifulSoup(resp.content, "lxml", from_encoding="utf-8")

            for table in soup.find_all("table"):
                ths = [th.get_text(strip=True) for th in table.find_all("th")]
                if "기관" not in ths or "외국인" not in ths:
                    continue
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) < 8:
                        continue
                    date_text = tds[0].get_text(strip=True)
                    if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_text):
                        continue

                    inst_text = tds[5].get_text(strip=True).replace(",", "")
                    frgn_text = tds[6].get_text(strip=True).replace(",", "")

                    try:
                        inst_val = int(inst_text)
                    except ValueError:
                        inst_val = 0
                    try:
                        frgn_val = int(frgn_text)
                    except ValueError:
                        frgn_val = 0

                    rows.append({
                        "date": pd.to_datetime(date_text),
                        "institution": inst_val,
                        "foreign": frgn_val,
                    })
                break
        except Exception:
            continue

    return pd.DataFrame(rows).drop_duplicates(subset="date").sort_values("date") if rows else pd.DataFrame()


def get_all_investor_summary(start_date: str) -> pd.DataFrame:
    results = []
    for sector, info in SECTOR_ETFS.items():
        inv_df = get_investor_trading(info["code"], pages=2)
        if inv_df.empty:
            continue

        inv_df = inv_df[inv_df["date"] >= start_date]
        if inv_df.empty:
            continue

        inst_total = inv_df["institution"].sum()
        frgn_total = inv_df["foreign"].sum()
        inst_recent = inv_df.tail(5)["institution"].sum()
        frgn_recent = inv_df.tail(5)["foreign"].sum()

        results.append({
            "sector": sector,
            "inst_total": inst_total,
            "frgn_total": frgn_total,
            "inst_recent_5d": inst_recent,
            "frgn_recent_5d": frgn_recent,
        })

    return pd.DataFrame(results) if results else pd.DataFrame()
