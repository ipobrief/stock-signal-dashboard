import os
import sqlite3
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from fund_lib import dart_client
from fund_lib.apikey import get_dart_key
from shared import gitsync

st.set_page_config(page_title="산업 자금흐름", page_icon="💸", layout="wide")
st.title("💸 산업 자금흐름 (기관·운용사 지분)")
st.caption("DART 대량보유보고(5%룰) — 운용사·연기금이 어느 산업/종목에 베팅하는지 추적")

REPORT_DB = os.path.join(os.path.dirname(__file__), "..", "data", "reports.db")
is_local = gitsync.is_local()


@st.dialog("💻 데이터 수집은 내 PC에서 해주세요")
def show_local_only_dialog():
    st.markdown("""
**클라우드(웹)에서는 수집한 데이터가 저장되지 않습니다.**

기관 지분 데이터를 갱신하려면 내 컴퓨터에서:

👉 `stock-dashboard` 폴더의 **`자금흐름_갱신.bat`** 를 **더블클릭**하세요.

→ DART 수집 + GitHub 푸시가 자동 진행되고, 1~2분 후 이 공개 앱에도 반영됩니다.
""")
    if st.button("확인", use_container_width=True):
        st.rerun()


# --- Sidebar: 수집 ---
with st.sidebar:
    st.header("데이터 수집")
    has_key = bool(get_dart_key())
    if is_local and not has_key:
        st.warning("DART API 키가 없습니다.")
    if st.button("📥 기관 지분 데이터 수집", use_container_width=True):
        if not is_local:
            show_local_only_dialog()
        else:
            conn = sqlite3.connect(REPORT_DB)
            rows = conn.execute("""
                SELECT stock_name, MAX(stock_code) code, sector
                FROM reports WHERE stock_code IS NOT NULL
                GROUP BY stock_name
            """).fetchall()
            conn.close()
            stocks = [{"stock_name": r[0], "stock_code": r[1], "sector": r[2]} for r in rows]

            key = get_dart_key()
            with st.spinner(f"{len(stocks)}개 종목 DART 조회 중... (수 분 소요)"):
                prog = st.progress(0)
                df = dart_client.collect_holdings(
                    key, stocks,
                    progress_callback=lambda i, t: prog.progress(i / t),
                )
                prog.empty()
                dart_client.save_holdings(df)
            st.success(f"{len(df)}건 수집 완료!")

            with st.spinner("GitHub 푸시 중..."):
                ok, msg = gitsync.push_data_files(["data/dart_holdings.json"], "데이터 갱신: 기관 지분")
            st.info(("✅ " if ok else "ℹ️ ") + msg)
            st.rerun()

    st.divider()
    st.subheader("필터")
    only_buying = st.toggle("지분 확대(매집)만 보기", value=True,
                            help="직전 보고 대비 지분율이 늘어난 건만 표시")
    min_ratio_chg = st.slider("최소 증가폭 (%p)", 0.0, 3.0, 0.0, 0.1)


# --- Load ---
holdings = dart_client.load_holdings()
if holdings.empty:
    if is_local:
        st.info("👈 사이드바에서 '기관 지분 데이터 수집'을 눌러 시작하세요.")
    else:
        st.info("아직 수집된 데이터가 없습니다. 로컬에서 `자금흐름_갱신.bat` 실행 후 갱신됩니다.")
    st.stop()

# 기관만
holdings["is_inst"] = holdings["holder"].apply(dart_client.is_institution)
inst = holdings[holdings["is_inst"]].copy()

st.caption(f"📊 기관/운용사 보유 {len(inst)}건 / {inst['stock_name'].nunique()}개 종목 / {inst['holder'].nunique()}개 기관")

# 필터 적용
view = inst.copy()
if only_buying:
    view = view[view["ratio_change"].notna() & (view["ratio_change"] > 0)]
view = view[view["ratio_change"].fillna(0) >= min_ratio_chg]

tab1, tab2, tab3 = st.tabs(["🏭 산업별 집중도", "🏢 운용사별 베팅", "📋 종목별 상세"])

# === 산업별 집중도 ===
with tab1:
    st.subheader("산업별 기관 자금 집중도")
    st.caption("기관이 매집 중인 종목/기관이 많은 산업 = 자금이 몰리는 산업")

    sec = view.groupby("sector").agg(
        stocks=("stock_name", "nunique"),
        institutions=("holder", "nunique"),
        avg_ratio_chg=("ratio_change", "mean"),
        records=("holder", "count"),
    ).reset_index().sort_values("records", ascending=False)

    if sec.empty:
        st.info("조건에 맞는 데이터가 없습니다.")
    else:
        fig = go.Figure(go.Bar(
            x=sec["records"], y=sec["sector"], orientation="h",
            marker_color="rgba(99,102,241,0.7)",
            text=sec["records"], textposition="outside",
        ))
        fig.update_layout(title="산업별 기관 매집 건수", height=max(400, len(sec) * 28),
                          yaxis=dict(autorange="reversed"), xaxis_title="기관 보고 건수")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            sec.rename(columns={
                "sector": "산업", "stocks": "종목수", "institutions": "기관수",
                "avg_ratio_chg": "평균증가폭(%p)", "records": "보고건수",
            }),
            use_container_width=True, hide_index=True,
            column_config={"평균증가폭(%p)": st.column_config.NumberColumn(format="%+.2f")},
        )

# === 운용사별 베팅 ===
with tab2:
    st.subheader("운용사·기관별 베팅 현황")
    st.caption("어떤 기관이 어느 종목·산업에 들어오고 있는지")

    holder_summary = view.groupby("holder").agg(
        stocks=("stock_name", "nunique"),
        sectors=("sector", "nunique"),
        avg_chg=("ratio_change", "mean"),
    ).reset_index().sort_values("stocks", ascending=False)

    hsel = st.dataframe(
        holder_summary.rename(columns={
            "holder": "기관", "stocks": "종목수", "sectors": "산업수", "avg_chg": "평균증가폭(%p)",
        }),
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={"평균증가폭(%p)": st.column_config.NumberColumn(format="%+.2f")},
    )

    if hsel and hsel.selection and hsel.selection.rows:
        hname = holder_summary.iloc[hsel.selection.rows[0]]["holder"]
        st.markdown(f"#### {hname} — 보유 종목")
        detail = view[view["holder"] == hname][["stock_name", "sector", "ratio", "ratio_change", "report_date"]]
        st.dataframe(
            detail.sort_values("ratio_change", ascending=False).rename(columns={
                "stock_name": "종목", "sector": "산업", "ratio": "보유비율(%)",
                "ratio_change": "증감(%p)", "report_date": "보고일",
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "보유비율(%)": st.column_config.NumberColumn(format="%.2f"),
                "증감(%p)": st.column_config.NumberColumn(format="%+.2f"),
            },
        )

# === 종목별 상세 ===
with tab3:
    st.subheader("종목별 기관 지분 (증가폭 큰 순)")
    detail = view.sort_values("ratio_change", ascending=False)[
        ["stock_name", "sector", "holder", "ratio", "ratio_change", "report_date"]
    ]
    st.dataframe(
        detail.rename(columns={
            "stock_name": "종목", "sector": "산업", "holder": "기관",
            "ratio": "보유비율(%)", "ratio_change": "증감(%p)", "report_date": "보고일",
        }),
        use_container_width=True, hide_index=True,
        column_config={
            "보유비율(%)": st.column_config.NumberColumn(format="%.2f"),
            "증감(%p)": st.column_config.NumberColumn(format="%+.2f"),
        },
    )
