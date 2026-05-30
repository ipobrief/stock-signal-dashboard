import pandas as pd
import numpy as np


def _norm(s: pd.Series) -> pd.Series:
    s = s.fillna(0).astype(float)
    rng = s.max() - s.min()
    if rng == 0:
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - s.min()) / rng


def institutional_buy_by_stock(holdings: pd.DataFrame) -> pd.DataFrame:
    """종목별 기관 매집(지분 증가) 집계."""
    if holdings.empty:
        return pd.DataFrame(columns=["stock_name", "inst_buy_count", "inst_buy_sum", "top_holders"])
    from fund_lib import dart_client
    h = holdings.copy()
    h["is_inst"] = h["holder"].apply(dart_client.is_institution)
    inst = h[h["is_inst"] & h["ratio_change"].notna() & (h["ratio_change"] > 0)]
    if inst.empty:
        return pd.DataFrame(columns=["stock_name", "inst_buy_count", "inst_buy_sum", "top_holders"])
    g = inst.groupby("stock_name").agg(
        inst_buy_count=("holder", "nunique"),
        inst_buy_sum=("ratio_change", "sum"),
        top_holders=("holder", lambda x: ", ".join(list(dict.fromkeys(x))[:3])),
    ).reset_index()
    return g


def sector_reco(signals: pd.DataFrame, holdings: pd.DataFrame, reports: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """업종 추천 랭킹: 애널리스트 관심 + 목표가 상향 시그널 + 기관 매집."""
    if signals.empty:
        return pd.DataFrame()

    # 섹터별 리포트수
    rep = reports.copy()
    sec_reports = rep.groupby("sector").agg(report_count=("id", "count"),
                                            stock_count=("stock_name", "nunique")).reset_index()
    # 섹터별 시그널 종목수(목표가 상향+빈도)
    sig = signals[signals["signal"]].groupby("sector").agg(signal_stocks=("stock_name", "nunique")).reset_index()

    # 섹터별 기관 매집 종목수
    inst = institutional_buy_by_stock(holdings)
    if not inst.empty and not reports.empty:
        name2sec = reports.dropna(subset=["sector"]).drop_duplicates("stock_name").set_index("stock_name")["sector"]
        inst = inst.copy()
        inst["sector"] = inst["stock_name"].map(name2sec)
        sec_inst = inst.dropna(subset=["sector"]).groupby("sector").agg(inst_buy_stocks=("stock_name", "nunique")).reset_index()
    else:
        sec_inst = pd.DataFrame(columns=["sector", "inst_buy_stocks"])

    df = sec_reports.merge(sig, on="sector", how="left").merge(sec_inst, on="sector", how="left")
    df["signal_stocks"] = df["signal_stocks"].fillna(0)
    df["inst_buy_stocks"] = df["inst_buy_stocks"].fillna(0)

    # 너무 작은 섹터(리포트 3건 미만) 제외 + '기타' 제외
    df = df[(df["report_count"] >= 3) & (df["sector"] != "기타")]
    if df.empty:
        return pd.DataFrame()

    df["score"] = (
        0.40 * _norm(df["report_count"]) +
        0.35 * _norm(df["signal_stocks"]) +
        0.25 * _norm(df["inst_buy_stocks"])
    ) * 100

    df = df.sort_values("score", ascending=False).head(top_n).reset_index(drop=True)

    def reason(r):
        parts = []
        parts.append(f"애널리스트 리포트 {int(r['report_count'])}건")
        if r["signal_stocks"] > 0:
            parts.append(f"목표가 상향 시그널 {int(r['signal_stocks'])}종목")
        if r["inst_buy_stocks"] > 0:
            parts.append(f"기관 매집 {int(r['inst_buy_stocks'])}종목")
        return " · ".join(parts)

    df["reason"] = df.apply(reason, axis=1)
    return df


def stock_reco(signals: pd.DataFrame, leading: pd.DataFrame, holdings: pd.DataFrame,
               top_sectors: list = None, top_n: int = 5) -> pd.DataFrame:
    """종목 추천 랭킹: 선행시그널 점수 + 기관 매집 + (옵션) 추천섹터 가중."""
    if signals.empty:
        return pd.DataFrame()

    base = signals[["stock_name", "stock_code", "sector", "total_reports",
                    "change_pct", "r_value", "last_3_avg", "signal"]].copy()

    # 선행시그널 점수
    if not leading.empty:
        lead = leading[["stock_name", "score", "attention_ratio", "new_brokers", "tp_raises"]].copy()
        base = base.merge(lead, on="stock_name", how="left")
    else:
        base["score"] = 0; base["attention_ratio"] = 0; base["new_brokers"] = 0; base["tp_raises"] = 0
    base["score"] = base["score"].fillna(0)

    # 기관 매집
    inst = institutional_buy_by_stock(holdings)
    base = base.merge(inst, on="stock_name", how="left")
    base["inst_buy_count"] = base["inst_buy_count"].fillna(0)
    base["inst_buy_sum"] = base["inst_buy_sum"].fillna(0)
    base["top_holders"] = base["top_holders"].fillna("")

    # 시그널 종목 위주
    base = base[base["signal"] | (base["score"] > 0) | (base["inst_buy_count"] > 0)]
    if base.empty:
        return pd.DataFrame()

    base["composite"] = (
        0.40 * _norm(base["score"]) +
        0.30 * _norm(base["inst_buy_count"]) +
        0.20 * _norm(base["total_reports"]) +
        0.10 * _norm(base["change_pct"].clip(lower=0))
    ) * 100

    # 추천 섹터 가중치
    if top_sectors:
        base.loc[base["sector"].isin(top_sectors), "composite"] *= 1.2

    base = base.sort_values("composite", ascending=False).head(top_n).reset_index(drop=True)

    def reason(r):
        parts = []
        if r["total_reports"]:
            parts.append(f"리포트 {int(r['total_reports'])}건")
        if r.get("attention_ratio", 0) and r["attention_ratio"] >= 1.5:
            parts.append(f"관심도 {r['attention_ratio']:.1f}배 급증")
        if r.get("tp_raises", 0) and r["tp_raises"] >= 2:
            parts.append(f"목표가 {int(r['tp_raises'])}회 상향")
        if r["inst_buy_count"] > 0:
            parts.append(f"기관 매집({r['top_holders']})")
        return " · ".join(parts) if parts else "복합 시그널 감지"

    base["reason"] = base.apply(reason, axis=1)
    return base
