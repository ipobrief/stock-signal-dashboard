import os
import sqlite3
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from fund_lib import dart_client, loan_client, trade_client, policy_client
from fund_lib.apikey import get_dart_key
from shared import gitsync

st.set_page_config(page_title="산업 자금흐름", page_icon="💸", layout="wide")
st.title("💸 산업 자금흐름")
st.caption("기관 지분(DART 5%룰) + 산업별 대출(한국은행) + 수출입(관세청)으로 어느 산업에 돈이 흐르는지 추적")

REPORT_DB = os.path.join(os.path.dirname(__file__), "..", "data", "reports.db")
is_local = gitsync.is_local()


@st.dialog("💻 데이터 수집은 내 PC에서 해주세요")
def show_local_only_dialog():
    st.markdown("""
**클라우드(웹)에서는 수집한 데이터가 저장되지 않습니다.**

데이터를 갱신하려면 내 컴퓨터에서:

👉 `stock-dashboard` 폴더의 **`자금흐름_갱신.bat`** 를 **더블클릭**하세요.

→ DART·대출·수출입 수집 + GitHub 푸시가 자동 진행되고, 1~2분 후 공개 앱에 반영됩니다.
""")
    if st.button("확인", use_container_width=True):
        st.rerun()


with st.sidebar:
    st.header("데이터")
    if st.button("📥 전체 데이터 수집", use_container_width=True):
        if not is_local:
            show_local_only_dialog()
        else:
            st.info("로컬에서는 `자금흐름_갱신.bat` 더블클릭을 권장합니다 (수 분 소요).")

# === 데이터 로드 ===
holdings = dart_client.load_holdings()
loans = loan_client.load_loans()
trade = trade_client.load_trade()
policy_df, policy_note = policy_client.load_policy()

tab_inst, tab_loan, tab_trade, tab_policy = st.tabs([
    "🏢 기관 지분 (5%룰)", "🏦 산업별 대출 (한국은행)", "🚢 수출입 (관세청)", "🏛️ 정책자금 (연1회)",
])

# ============ 기관 지분 ============
with tab_inst:
    if holdings.empty:
        st.info("기관 지분 데이터가 없습니다. 로컬에서 `자금흐름_갱신.bat` 실행 후 표시됩니다.")
    else:
        holdings["is_inst"] = holdings["holder"].apply(dart_client.is_institution)
        inst = holdings[holdings["is_inst"]].copy()
        st.caption(f"기관/운용사 보유 {len(inst)}건 / {inst['stock_name'].nunique()}개 종목 / {inst['holder'].nunique()}개 기관")

        c1, c2 = st.columns(2)
        only_buying = c1.toggle("지분 확대(매집)만", value=True)
        min_chg = c2.slider("최소 증가폭(%p)", 0.0, 3.0, 0.0, 0.1)

        view = inst.copy()
        if only_buying:
            view = view[view["ratio_change"].notna() & (view["ratio_change"] > 0)]
        view = view[view["ratio_change"].fillna(0) >= min_chg]

        sub1, sub2, sub3 = st.tabs(["산업별 집중도", "운용사별 베팅", "종목별 상세"])

        with sub1:
            sec = view.groupby("sector").agg(
                stocks=("stock_name", "nunique"), institutions=("holder", "nunique"),
                avg_chg=("ratio_change", "mean"), records=("holder", "count"),
            ).reset_index().sort_values("records", ascending=False)
            if not sec.empty:
                fig = go.Figure(go.Bar(x=sec["records"], y=sec["sector"], orientation="h",
                                       marker_color="rgba(99,102,241,0.7)", text=sec["records"], textposition="outside"))
                fig.update_layout(title="산업별 기관 매집 건수", height=max(400, len(sec)*26),
                                  yaxis=dict(autorange="reversed"), xaxis_title="보고 건수")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(sec.rename(columns={"sector":"산업","stocks":"종목수","institutions":"기관수","avg_chg":"평균증가폭(%p)","records":"보고건수"}),
                             use_container_width=True, hide_index=True,
                             column_config={"평균증가폭(%p)": st.column_config.NumberColumn(format="%+.2f")})

        with sub2:
            hs = view.groupby("holder").agg(stocks=("stock_name","nunique"), sectors=("sector","nunique"), avg_chg=("ratio_change","mean")).reset_index().sort_values("stocks", ascending=False)
            hsel = st.dataframe(hs.rename(columns={"holder":"기관","stocks":"종목수","sectors":"산업수","avg_chg":"평균증가폭(%p)"}),
                                use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
                                column_config={"평균증가폭(%p)": st.column_config.NumberColumn(format="%+.2f")})
            if hsel and hsel.selection and hsel.selection.rows:
                hn = hs.iloc[hsel.selection.rows[0]]["holder"]
                st.markdown(f"#### {hn} — 보유 종목")
                dd = view[view["holder"]==hn][["stock_name","sector","ratio","ratio_change","report_date"]].sort_values("ratio_change", ascending=False)
                st.dataframe(dd.rename(columns={"stock_name":"종목","sector":"산업","ratio":"보유비율(%)","ratio_change":"증감(%p)","report_date":"보고일"}),
                             use_container_width=True, hide_index=True,
                             column_config={"보유비율(%)": st.column_config.NumberColumn(format="%.2f"),"증감(%p)": st.column_config.NumberColumn(format="%+.2f")})

        with sub3:
            dd = view.sort_values("ratio_change", ascending=False)[["stock_name","sector","holder","ratio","ratio_change","report_date"]]
            st.dataframe(dd.rename(columns={"stock_name":"종목","sector":"산업","holder":"기관","ratio":"보유비율(%)","ratio_change":"증감(%p)","report_date":"보고일"}),
                         use_container_width=True, hide_index=True,
                         column_config={"보유비율(%)": st.column_config.NumberColumn(format="%.2f"),"증감(%p)": st.column_config.NumberColumn(format="%+.2f")})

# ============ 산업별 대출 ============
with tab_loan:
    st.subheader("산업별 대출 증감 (예금은행, 분기)")
    st.caption("대출이 늘어난 산업 = 자금이 유입되는 산업 (한국은행 ECOS)")
    if loans.empty:
        st.info("대출 데이터가 없습니다. 로컬에서 `자금흐름_갱신.bat` 실행 후 표시됩니다.")
    else:
        # 합계행 제외
        d = loans[~loans["industry"].str.contains("산업별대출금|총계", na=False)].copy()
        d = d[d["loan_change_pct"].notna()].sort_values("loan_change_pct", ascending=False)
        if not d.empty:
            period = f"{d.iloc[0]['prev_q']} → {d.iloc[0]['recent_q']}"
            st.caption(f"기간: {period}")
            top = d.head(20)
            fig = go.Figure(go.Bar(
                x=top["loan_change_pct"], y=top["industry"], orientation="h",
                marker_color=["rgba(34,197,94,0.7)" if v>0 else "rgba(239,68,68,0.7)" for v in top["loan_change_pct"]],
                text=[f"{v:+.2f}%" for v in top["loan_change_pct"]], textposition="outside",
            ))
            fig.update_layout(title="산업별 대출 증감률 (상위 20)", height=600,
                              yaxis=dict(autorange="reversed"), xaxis_title="대출 증감률 (%)")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                d.rename(columns={"industry":"산업","loan_now":"대출잔액(십억)","loan_change_pct":"증감률(%)"})[["산업","대출잔액(십억)","증감률(%)"]],
                use_container_width=True, hide_index=True,
                column_config={"대출잔액(십억)": st.column_config.NumberColumn(format="%,.0f"),
                               "증감률(%)": st.column_config.NumberColumn(format="%+.2f")},
            )

# ============ 수출입 ============
with tab_trade:
    st.subheader("산업별 수출 증감 (관세청)")
    st.caption("수출이 늘어난 산업 = 실물경기 개선 선행지표")
    if trade.empty:
        st.info("수출입 데이터가 없습니다. (관세청 API 승인 후 `자금흐름_갱신.bat` 실행 시 표시)")
    else:
        d = trade[trade["export_change_pct"].notna()].sort_values("export_change_pct", ascending=False)
        fig = go.Figure(go.Bar(
            x=d["export_change_pct"], y=d["industry"], orientation="h",
            marker_color=["rgba(34,197,94,0.7)" if v>0 else "rgba(239,68,68,0.7)" for v in d["export_change_pct"]],
            text=[f"{v:+.1f}%" for v in d["export_change_pct"]], textposition="outside",
        ))
        fig.update_layout(title="산업별 수출 증감률", height=max(400, len(d)*26),
                          yaxis=dict(autorange="reversed"), xaxis_title="수출 증감률 (%)")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            d.rename(columns={"industry":"산업","export_now":"수출액($)","export_change_pct":"증감률(%)"})[["산업","수출액($)","증감률(%)"]],
            use_container_width=True, hide_index=True,
            column_config={"수출액($)": st.column_config.NumberColumn(format="%,.0f"),
                           "증감률(%)": st.column_config.NumberColumn(format="%+.1f")},
        )

# ============ 정책자금 ============
with tab_policy:
    st.subheader("정책자금 지원 현황")
    st.caption("⚠️ 연 1회 갱신 — 중소벤처기업진흥공단 (정부 정책자금이 어디에 배정됐는지: 자금종류/업종별)")

    if is_local:
        with st.expander("📤 정책자금 CSV 업로드 (연 1회)"):
            st.markdown("[data.go.kr 15069962](https://www.data.go.kr/data/15069962/fileData.do)에서 CSV 다운로드 후 업로드하세요.")
            up = st.file_uploader("업종별 정책자금 CSV/엑셀", type=["csv", "xlsx", "xls"])
            note = st.text_input("기준 시점 메모 (예: 2024년)", value="")
            if up is not None and st.button("저장 및 반영"):
                try:
                    pdf = policy_client.parse_policy_csv(up)
                    policy_client.save_policy(pdf, note or "연 1회 갱신")
                    ok, msg = gitsync.push_data_files(["data/policy_fund.json"], "데이터 갱신: 정책자금")
                    st.success(f"{len(pdf)}개 업종 저장 완료. {msg}")
                    st.rerun()
                except Exception as e:
                    st.error(f"파싱 실패: {e}")

    if policy_df.empty:
        st.info("정책자금 데이터가 없습니다. (로컬에서 CSV 업로드 시 표시 — 연 1회 갱신)")
    else:
        if policy_note:
            st.caption(f"📅 기준: {policy_note}")
        has_amt = policy_df["amount"].notna().any()
        sort_col = "amount" if has_amt else "count"
        d = policy_df[policy_df[sort_col].notna()].sort_values(sort_col, ascending=False).head(25)
        if not d.empty:
            fig = go.Figure(go.Bar(
                x=d[sort_col], y=d["industry"], orientation="h",
                marker_color="rgba(168,85,247,0.7)",
                text=[f"{v:,.0f}" for v in d[sort_col]], textposition="outside",
            ))
            fig.update_layout(title="정책자금 " + ("지원금액" if has_amt else "지원건수") + " (상위 25)",
                              height=max(400, len(d)*26), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

        show = policy_df.rename(columns={"industry": "업종", "amount": "지원금액", "count": "지원건수"})
        cols = ["업종"] + [c for c in ["지원금액", "지원건수"] if c in show.columns and show[c].notna().any()]
        st.dataframe(show[cols], use_container_width=True, hide_index=True,
                     column_config={"지원금액": st.column_config.NumberColumn(format="%,.0f"),
                                    "지원건수": st.column_config.NumberColumn(format="%,.0f")})
