import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

from signal_lib.db import init_db, get_reports
from signal_lib.analysis import compute_signals, compute_leading_signals, get_stock_target_history
from signal_lib.stock_price import get_stock_price
from fund_lib import dart_client
from reco_lib import engine
from shared import watchlist as wl

st.set_page_config(page_title="종합 추천", page_icon="🎯", layout="wide")
init_db()

st.title("🎯 종합 추천 (탑다운)")
st.caption("애널리스트 리포트 + 목표가 시그널 + 기관 매집을 종합해 추천 업종·종목 TOP5를 선정합니다")

# --- 데이터 ---
df_all = get_reports()
if df_all.empty:
    st.info("리포트 데이터가 없습니다.")
    st.stop()

import pandas as _pd
data_max = _pd.to_datetime(df_all["report_date"]).max().date()
with st.sidebar:
    st.header("분석 기간")
    start_date = st.date_input("시작일", value=max(_pd.to_datetime(df_all["report_date"]).min().date(), data_max - timedelta(days=90)))
    top_n = st.slider("TOP N", 3, 10, 5)

df = df_all[_pd.to_datetime(df_all["report_date"]).dt.date >= start_date].copy()

signals = compute_signals(df, min_reports=5)
leading = compute_leading_signals(df, min_reports=3)
holdings = dart_client.load_holdings()

sec_reco = engine.sector_reco(signals, holdings, df, top_n=top_n)
top_sectors = sec_reco["sector"].tolist() if not sec_reco.empty else []
stk_reco = engine.stock_reco(signals, leading, holdings, top_sectors=top_sectors, top_n=top_n)

# ============ 추천 업종 ============
st.subheader(f"🏭 추천 업종 TOP {top_n}")
if sec_reco.empty:
    st.info("추천할 업종이 부족합니다. 기간을 늘려보세요.")
else:
    for i, r in sec_reco.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([1, 5])
            c1.metric(f"#{i+1}", r["sector"], f"{r['score']:.0f}점")
            c2.markdown(f"**{r['sector']}**  \n{r['reason']}")

st.divider()

# ============ 추천 종목 ============
st.subheader(f"⭐ 추천 종목 TOP {top_n}")
if stk_reco.empty:
    st.info("추천할 종목이 부족합니다.")
    st.stop()

for i, r in stk_reco.iterrows():
    in_top_sector = r["sector"] in top_sectors
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.metric(f"#{i+1}", r["stock_name"], f"{r['composite']:.0f}점")
        badge = "🔥 추천업종" if in_top_sector else ""
        c2.markdown(f"**{r['stock_name']}** ({r['sector']}) {badge}  \n{r['reason']}")
        c2.caption(f"최근 목표가 {int(r['last_3_avg']):,}원 · 목표가 추세 {r['change_pct']:+.1f}%")
        if not wl.is_in_watchlist(r["stock_name"]):
            if c3.button("⭐ 관심", key=f"wl_{r['stock_name']}", use_container_width=True):
                wl.add_stock(r["stock_name"], r["stock_code"])
                st.rerun()
        else:
            c3.success("✅")

st.divider()

# ============ 종합 종목 카드 ============
st.subheader("🔎 종합 종목 카드")
st.caption("한 종목의 3개 관점(리포트·섹터·기관 지분)을 한 번에")

pick = st.selectbox("종목 선택", stk_reco["stock_name"].tolist())
if pick:
    row = stk_reco[stk_reco["stock_name"] == pick].iloc[0]
    code = row["stock_code"]

    # 1) 리포트/목표가
    hist = get_stock_target_history(df, pick)
    latest_target = int(row["last_3_avg"]) if pd.notna(row["last_3_avg"]) else None
    cur = None
    if code:
        pdf = get_stock_price(code, start_date.strftime("%Y-%m-%d"), data_max.strftime("%Y-%m-%d"))
        if not pdf.empty:
            cur = int(pdf.iloc[-1]["close"])
    upside = round((latest_target - cur) / cur * 100, 1) if (latest_target and cur) else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("소속 업종", row["sector"], "🔥 추천" if row["sector"] in top_sectors else "")
    m2.metric("현재가", f"{cur:,}원" if cur else "N/A")
    m3.metric("최근 목표가", f"{latest_target:,}원" if latest_target else "N/A")
    m4.metric("괴리율(상승여력)", f"{upside:+.1f}%" if upside is not None else "N/A")

    cc1, cc2 = st.columns(2)

    with cc1:
        st.markdown("**📈 목표가 vs 주가**")
        if not hist.empty:
            fig = go.Figure()
            if code and 'pdf' in dir() and not pdf.empty:
                fig.add_trace(go.Scatter(x=pdf["date"], y=pdf["close"], mode="lines",
                                         line=dict(color="rgba(34,197,94,0.8)", width=1.5),
                                         fill="tozeroy", fillcolor="rgba(34,197,94,0.1)", name="주가"))
            fig.add_trace(go.Scatter(x=hist["report_date"], y=hist["target_price"], mode="markers",
                                     marker=dict(size=8, color="royalblue"), name="목표가"))
            fig.update_layout(height=300, showlegend=False, margin=dict(t=10, b=10), yaxis=dict(tickformat=","))
            st.plotly_chart(fig, use_container_width=True)

    with cc2:
        st.markdown("**🏢 기관 지분 현황 (5%룰)**")
        h = holdings[holdings["stock_name"] == pick] if not holdings.empty else pd.DataFrame()
        if not h.empty:
            h2 = h.copy()
            h2["is_inst"] = h2["holder"].apply(dart_client.is_institution)
            hi = h2[h2["is_inst"]][["holder", "ratio", "ratio_change", "report_date"]].sort_values("ratio_change", ascending=False)
            if not hi.empty:
                st.dataframe(hi.rename(columns={"holder": "기관", "ratio": "보유%", "ratio_change": "증감%p", "report_date": "보고일"}),
                             use_container_width=True, hide_index=True,
                             column_config={"보유%": st.column_config.NumberColumn(format="%.2f"),
                                            "증감%p": st.column_config.NumberColumn(format="%+.2f")})
            else:
                st.caption("기관 지분 5%룰 보고 없음")
        else:
            st.caption("기관 지분 데이터 없음")

    st.info(f"**추천 이유:** {row['reason']}")
