import re
import requests
import pandas as pd


def get_stock_price(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    if not stock_code:
        return pd.DataFrame()

    start = start_date.replace("-", "")
    end = end_date.replace("-", "")

    url = "https://fchart.stock.naver.com/siseJson.nhn"
    params = {
        "symbol": stock_code,
        "requestType": "1",
        "startTime": start,
        "endTime": end,
        "timeframe": "day",
    }

    try:
        resp = requests.get(url, params=params, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.encoding = "utf-8"
        text = resp.text

        rows = []
        for match in re.finditer(r'\["(\d{8})",\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),', text):
            date_str, open_p, high, low, close = match.groups()
            rows.append({
                "date": pd.to_datetime(date_str),
                "close": int(close),
            })

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()
