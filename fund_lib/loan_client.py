import os
import requests
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOAN_PATH = os.path.join(DATA_DIR, "industry_loan.json")
KEY_PATH = os.path.join(DATA_DIR, "ecos_key.txt")

STAT_CODE = "131Y013"  # 예금은행 산업별 대출금 (분기)


def get_ecos_key() -> str:
    env = os.environ.get("ECOS_KEY")
    if env:
        return env.strip()
    try:
        import streamlit as st
        if "ECOS_KEY" in st.secrets:
            return str(st.secrets["ECOS_KEY"]).strip()
    except Exception:
        pass
    if os.path.exists(KEY_PATH):
        return open(KEY_PATH, encoding="utf-8").read().strip()
    return ""


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_quarter(api_key: str, quarter: str) -> dict:
    """특정 분기(예 2026Q1)의 산업별 대출잔액 {산업명: 금액(십억원)}."""
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/200/{STAT_CODE}/Q/{quarter}/{quarter}"
    try:
        r = requests.get(url, timeout=20)
        rows = r.json().get("StatisticSearch", {}).get("row", [])
        result = {}
        for x in rows:
            name = x.get("ITEM_NAME1", "").strip()
            val = _num(x.get("DATA_VALUE"))
            if name and val is not None:
                result[name] = val
        return result
    except Exception:
        return {}


def collect_loans(api_key: str, recent_q: str, prev_q: str) -> pd.DataFrame:
    """최근/직전 분기 산업별 대출 + 증감 계산."""
    now = fetch_quarter(api_key, recent_q)
    prev = fetch_quarter(api_key, prev_q)
    if not now:
        return pd.DataFrame()

    rows = []
    for name, amt in now.items():
        prev_amt = prev.get(name)
        chg = ((amt - prev_amt) / prev_amt * 100) if (prev_amt and prev_amt > 0) else None
        rows.append({
            "industry": name,
            "loan_now": amt,                 # 십억원
            "loan_prev": prev_amt,
            "loan_change_pct": round(chg, 2) if chg is not None else None,
            "recent_q": recent_q, "prev_q": prev_q,
        })
    df = pd.DataFrame(rows)
    # '산업별대출금' 같은 합계행은 별도 표시 위해 유지
    return df


def save_loans(df: pd.DataFrame):
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_json(LOAN_PATH, orient="records", force_ascii=False)


def load_loans() -> pd.DataFrame:
    if not os.path.exists(LOAN_PATH):
        return pd.DataFrame()
    try:
        return pd.read_json(LOAN_PATH, orient="records")
    except Exception:
        return pd.DataFrame()


def latest_quarters(n_back: int = 1):
    """현재 기준 최근 분기와 n_back분기 전 (YYYYQq) 반환."""
    import datetime
    now = datetime.date.today()
    q = (now.month - 1) // 3 + 1
    y = now.year
    # 최근 확정 분기는 보통 1분기 전
    def shift(y, q, back):
        idx = y * 4 + (q - 1) - back
        return idx // 4, idx % 4 + 1
    ry, rq = shift(y, q, 1)
    py, pq = shift(y, q, 1 + n_back)
    return f"{ry}Q{rq}", f"{py}Q{pq}"
