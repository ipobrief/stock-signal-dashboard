import os
import io
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
POLICY_PATH = os.path.join(DATA_DIR, "policy_fund.json")

# 업종/금액 컬럼 자동 감지 키워드
INDUSTRY_KEYS = ["업종", "산업", "분류", "구분"]
AMOUNT_KEYS = ["금액", "지원", "융자", "실적", "규모", "공급"]
COUNT_KEYS = ["건수", "업체", "기업수", "개수"]


def _read_any(file) -> pd.DataFrame:
    """CSV/Excel 자동 판별 읽기 (한글 인코딩 대응)."""
    name = getattr(file, "name", "").lower()
    raw = file.read() if hasattr(file, "read") else open(file, "rb").read()

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))

    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception:
            continue
    raise ValueError("CSV를 읽을 수 없습니다.")


def parse_policy_csv(file) -> pd.DataFrame:
    """정책자금 업종별 지원현황 CSV → [industry, amount, count] 표준화."""
    df = _read_any(file)
    cols = list(df.columns)

    def find(keys):
        for c in cols:
            if any(k in str(c) for k in keys):
                return c
        return None

    ind_col = find(INDUSTRY_KEYS)
    amt_col = find(AMOUNT_KEYS)
    cnt_col = find(COUNT_KEYS)

    if not ind_col:
        # 첫 텍스트 컬럼을 업종으로
        ind_col = cols[0]

    out = pd.DataFrame()
    out["industry"] = df[ind_col].astype(str).str.strip()

    def to_num(series):
        return pd.to_numeric(
            series.astype(str).str.replace(",", "").str.replace(r"[^0-9.\-]", "", regex=True),
            errors="coerce",
        )

    out["amount"] = to_num(df[amt_col]) if amt_col else None
    out["count"] = to_num(df[cnt_col]) if cnt_col else None

    out = out[out["industry"].notna() & (out["industry"] != "")]
    out = out[out["industry"].str.len() <= 30]  # 합계/주석행 등 제거 보조
    return out.reset_index(drop=True)


def save_policy(df: pd.DataFrame, source_note: str = ""):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"note": source_note, "records": df.to_dict(orient="records")}
    import json
    with open(POLICY_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def load_policy() -> tuple:
    """(df, note) 반환."""
    if not os.path.exists(POLICY_PATH):
        return pd.DataFrame(), ""
    try:
        import json
        with open(POLICY_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return pd.DataFrame(d.get("records", [])), d.get("note", "")
    except Exception:
        return pd.DataFrame(), ""
