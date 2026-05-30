import os
import io
import zipfile
import json
import time
import xml.etree.ElementTree as ET
import requests
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CORP_MAP_PATH = os.path.join(DATA_DIR, "dart_corp_map.json")
HOLDINGS_PATH = os.path.join(DATA_DIR, "dart_holdings.json")


def save_holdings(df: pd.DataFrame):
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_json(HOLDINGS_PATH, orient="records", force_ascii=False)


def load_holdings() -> pd.DataFrame:
    if not os.path.exists(HOLDINGS_PATH):
        return pd.DataFrame()
    try:
        return pd.read_json(HOLDINGS_PATH, orient="records")
    except Exception:
        return pd.DataFrame()

BASE = "https://opendart.fss.or.kr/api"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def get_corp_code_map(api_key: str, force: bool = False) -> dict:
    """종목코드(6자리) → DART 기업코드(8자리) 매핑. 최초 1회 다운로드 후 캐시."""
    if not force and os.path.exists(CORP_MAP_PATH):
        try:
            with open(CORP_MAP_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = f"{BASE}/corpCode.xml"
    resp = requests.get(url, params={"crtfc_key": api_key}, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()

    # 응답이 zip(xml) 또는 에러json
    if resp.headers.get("content-type", "").startswith("application/json") or resp.content[:1] == b"{":
        raise RuntimeError(f"DART 응답 오류: {resp.text[:200]}")

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_data = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_data)

    mapping = {}
    for item in root.iter("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            mapping[stock_code] = corp_code

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CORP_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f)
    return mapping


def get_major_holders(api_key: str, corp_code: str) -> pd.DataFrame:
    """특정 기업의 대량보유 상황보고(5%룰) 목록."""
    url = f"{BASE}/majorstock.json"
    try:
        resp = requests.get(url, params={"crtfc_key": api_key, "corp_code": corp_code},
                            timeout=15, headers={"User-Agent": USER_AGENT})
        data = resp.json()
    except Exception:
        return pd.DataFrame()

    if data.get("status") != "000":
        return pd.DataFrame()

    rows = data.get("list", [])
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _to_float(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None


def collect_holdings(api_key: str, stocks: list, progress_callback=None) -> pd.DataFrame:
    """stocks: [{'stock_name','stock_code','sector'}] 리스트.
    각 종목의 최신 대량보유 보고를 모아 반환."""
    corp_map = get_corp_code_map(api_key)
    results = []
    total = len(stocks)

    for i, s in enumerate(stocks):
        if progress_callback:
            progress_callback(i + 1, total)

        code = s.get("stock_code")
        if not code:
            continue
        corp_code = corp_map.get(str(code).zfill(6))
        if not corp_code:
            continue

        df = get_major_holders(api_key, corp_code)
        if df.empty:
            continue

        # 보고자(repror)별 최신 보고만 사용
        df = df.sort_values("rcept_dt")
        latest = df.groupby("repror", as_index=False).last()

        for _, r in latest.iterrows():
            ratio = _to_float(r.get("stkrt"))
            ratio_chg = _to_float(r.get("stkrt_irds"))
            if ratio is None:
                continue
            results.append({
                "stock_name": s.get("stock_name"),
                "stock_code": code,
                "sector": s.get("sector", "기타"),
                "holder": r.get("repror"),          # 보고자(운용사/기관)
                "ratio": ratio,                      # 보유비율 %
                "ratio_change": ratio_chg,           # 직전 대비 증감 %p
                "report_date": r.get("rcept_dt"),
                "reason": r.get("report_resn"),
            })

        time.sleep(0.05)

    return pd.DataFrame(results)


# 운용사/기관 키워드 (보고자명에 포함되면 기관투자자로 분류)
INSTITUTION_KEYWORDS = [
    "자산운용", "투자자문", "운용", "캐피탈", "벤처", "인베스트", "파트너스",
    "국민연금", "연기금", "공제회", "생명", "화재", "증권", "은행", "보험",
    "Capital", "Asset", "Management", "Partners", "Investment",
]


def is_institution(holder: str) -> bool:
    if not holder:
        return False
    return any(kw in holder for kw in INSTITUTION_KEYWORDS)
