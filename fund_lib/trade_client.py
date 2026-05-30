import os
import time
import requests
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TRADE_PATH = os.path.join(DATA_DIR, "customs_trade.json")
KEY_PATH = os.path.join(DATA_DIR, "datagokr_key.txt")

# 관세청 품목별 수출입실적 (data.go.kr 15101609)
ENDPOINT = "http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"

# HS 2단위 코드 → 산업 분류 (주요 산업만)
HS2_TO_INDUSTRY = {
    "85": "반도체·전자", "84": "기계·컴퓨터", "87": "자동차", "90": "정밀기기",
    "27": "에너지·석유", "29": "화학", "39": "플라스틱", "72": "철강", "73": "철강제품",
    "30": "의약품", "88": "항공·우주", "89": "조선", "71": "귀금속",
    "40": "고무", "03": "수산물", "08": "과일", "22": "음료·주류",
    "94": "가구", "61": "의류(편물)", "62": "의류(직물)", "64": "신발",
    "33": "화장품", "48": "제지", "76": "알루미늄", "74": "구리",
}


def get_datagokr_key() -> str:
    env = os.environ.get("DATAGOKR_KEY")
    if env:
        return env.strip()
    try:
        import streamlit as st
        if "DATAGOKR_KEY" in st.secrets:
            return str(st.secrets["DATAGOKR_KEY"]).strip()
    except Exception:
        pass
    if os.path.exists(KEY_PATH):
        return open(KEY_PATH, encoding="utf-8").read().strip()
    return ""


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def fetch_trade(api_key: str, start_yymm: str, end_yymm: str, hs2: str) -> dict:
    """특정 HS 2단위 품목군의 기간 수출입 합계(달러). 하위 품목 전체 합산."""
    try:
        resp = requests.get(ENDPOINT, params={
            "serviceKey": api_key, "strtYymm": start_yymm,
            "endYymm": end_yymm, "hsSgn": hs2,
        }, timeout=25)
        if resp.status_code != 200:
            return {}
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        exp = imp = 0.0
        for item in root.iter("item"):
            exp += _num(item.findtext("expDlr")) or 0
            imp += _num(item.findtext("impDlr")) or 0
        if exp == 0 and imp == 0:
            return {}
        return {"export": exp, "import": imp}
    except Exception:
        return {}


def collect_trade(api_key: str, recent_yymm: str, prev_yymm: str,
                  progress_callback=None) -> pd.DataFrame:
    """주요 산업(HS2)별 최근/직전 기간 수출입을 수집해 증감 계산.
    recent_yymm/prev_yymm: 'YYYYMM' (각 기간의 시작=끝 1개월)."""
    rows = []
    items = list(HS2_TO_INDUSTRY.items())
    for i, (hs2, industry) in enumerate(items):
        if progress_callback:
            progress_callback(i + 1, len(items))

        recent = fetch_trade(api_key, recent_yymm, recent_yymm, hs2)
        prev = fetch_trade(api_key, prev_yymm, prev_yymm, hs2)
        if not recent:
            continue

        exp_now = recent.get("export", 0)
        exp_prev = prev.get("export", 0) if prev else 0
        chg = ((exp_now - exp_prev) / exp_prev * 100) if exp_prev > 0 else None

        rows.append({
            "hs2": hs2, "industry": industry,
            "export_now": exp_now, "export_prev": exp_prev,
            "export_change_pct": round(chg, 1) if chg is not None else None,
            "import_now": recent.get("import", 0),
        })
        time.sleep(0.1)

    return pd.DataFrame(rows)


def save_trade(df: pd.DataFrame):
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_json(TRADE_PATH, orient="records", force_ascii=False)


def load_trade() -> pd.DataFrame:
    if not os.path.exists(TRADE_PATH):
        return pd.DataFrame()
    try:
        return pd.read_json(TRADE_PATH, orient="records")
    except Exception:
        return pd.DataFrame()
