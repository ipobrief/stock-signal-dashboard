import re
import requests
import pandas as pd
from sector_lib.config import USER_AGENT


def get_stock_price(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    if not code:
        return pd.DataFrame()
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
        for match in re.finditer(r'\["(\d{8})",\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)', resp.text):
            date_str, open_p, high, low, close = match.groups()
            rows.append({"date": pd.to_datetime(date_str), "close": int(close)})
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_return_and_current(code: str, start_date: str, end_date: str) -> tuple:
    """기간 수익률(%)과 현재가 반환"""
    df = get_stock_price(code, start_date, end_date)
    if df.empty or len(df) < 2:
        return None, None
    first = df.iloc[0]["close"]
    last = df.iloc[-1]["close"]
    returns = (last - first) / first * 100 if first > 0 else None
    return (round(returns, 1) if returns is not None else None), int(last)
