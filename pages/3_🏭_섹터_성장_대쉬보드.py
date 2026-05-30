import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from sector_lib.config import SECTOR_ETFS, SECTOR_TO_REPORT
from sector_lib import data_fetcher
from shared import watchlist as wl
from sector_lib.stock_price import get_return_and_current

st.set_page_config(page_title="섹터 성장 대쉬보드", page_icon="🏭", layout="wide")


@st.cache_data(ttl=1800)
def get_sector_etf_summary(start_date, end_date):
    return data_fetcher.get_sector_etf_summary(start_date, end_date)


@st.cache_data(ttl=1800)
def get_all_investor_summary(start_date):
    return data_fetcher.get_all_investor_summary(start_date)


@st.cache_data(ttl=1800)
def get_etf_price(code, start_date, end_date):
    return data_fetcher.get_etf_price(code, start_date, end_date)


@st.cache_data(ttl=1800)
def get_investor_trading(code, pages=5):
    return data_fetcher.get_investor_trading(code, pages)


@st.cache_data(ttl=600)
def get_sector_rankings():
    return data_fetcher.get_sector_rankings()

st.title("🏭 섹터 성장 대쉬보드")
st.caption("어떤 산업에 돈이 몰리고 있는가? — 섹터ETF 수익률 + 거래대금 + 리포트 집중도")

# --- Sidebar ---
with st.sidebar:
    st.header("분석 기간")
    period = st.selectbox("기간 선택", ["1개월", "3개월", "6개월", "1년"], index=1)
    period_days = {"1개월": 30, "3개월": 90, "6개월": 180, "1년": 365}[period]
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")

    st.caption(f"📅 {start_date} ~ {end_date}")

    # 리포트 데이터 연동
    st.divider()
    st.subheader("리포트 데이터 연동")
    import os
    report_db_path = os.path.join(os.path.dirname(__file__), "..", "data", "reports.db")
    has_report_db = os.path.exists(report_db_path)
    if has_report_db:
        st.success("✅ 리포트 DB 연결됨")
    else:
        st.warning("리포트 DB 없음")


# --- Main ---
with st.spinner("섹터 ETF 데이터 수집 중..."):
    summary_df = get_sector_etf_summary(start_date, end_date)

if summary_df.empty:
    st.error("데이터를 가져올 수 없습니다.")
    st.stop()

# === 리포트 데이터 연동 ===
report_sector_df = pd.DataFrame()
if has_report_db:
    try:
        import sqlite3
        conn = sqlite3.connect(report_db_path)
        report_df = pd.read_sql_query(
            f"SELECT sector, stock_name, report_date, broker FROM reports WHERE report_date >= '{start_date}'",
            conn,
        )
        conn.close()

        if not report_df.empty:
            report_sector_df = report_df.groupby("sector").agg(
                report_count=("stock_name", "count"),
                unique_stocks=("stock_name", "nunique"),
                unique_brokers=("broker", "nunique"),
            ).reset_index()
    except Exception:
        pass

# === 관심종목 현황 ===
watch_items = wl.load_watchlist()
with st.expander(f"⭐ 관심종목 ({len(watch_items)}개)", expanded=bool(watch_items)):
    if not watch_items:
        st.caption("아직 관심종목이 없습니다. 섹터별 종목 테이블에서 종목을 클릭해 추가하세요.")
    else:
        @st.cache_data(ttl=300)
        def get_latest_target(stock_name):
            if not has_report_db:
                return None
            import sqlite3
            conn = sqlite3.connect(report_db_path)
            row = conn.execute(
                "SELECT target_price FROM reports WHERE stock_name=? AND target_price IS NOT NULL ORDER BY report_date DESC LIMIT 1",
                (stock_name,),
            ).fetchone()
            conn.close()
            return row[0] if row else None

        watch_rows = []
        for it in watch_items:
            name = it["stock_name"]
            code = it.get("stock_code")
            ret, cur = get_return_and_current(code, start_date, end_date) if code else (None, None)
            target = get_latest_target(name)
            upside = round((target - cur) / cur * 100, 1) if (target and cur and cur > 0) else None
            watch_rows.append({
                "종목": name,
                f"수익률({period})": ret,
                "현재가": cur,
                "목표가": target,
                "괴리율(상승여력)": upside,
            })

        watch_df = pd.DataFrame(watch_rows).sort_values("괴리율(상승여력)", ascending=False, na_position="last")

        st.dataframe(
            watch_df, use_container_width=True, hide_index=True,
            column_config={
                f"수익률({period})": st.column_config.NumberColumn(format="%.1f%%"),
                "현재가": st.column_config.NumberColumn(format="%,d원"),
                "목표가": st.column_config.NumberColumn(format="%,d원"),
                "괴리율(상승여력)": st.column_config.NumberColumn(format="%+.1f%%", help="목표가 대비 현재가 — 클수록 상승 여력"),
            },
        )

        remove_target = st.selectbox("관심종목 삭제", [""] + [it["stock_name"] for it in watch_items], key="remove_sel")
        if st.button("🗑️ 삭제") and remove_target:
            wl.remove_stock(remove_target)
            st.rerun()

# === 투자자별 매매동향 ===
with st.spinner("투자자별 매매동향 수집 중..."):
    investor_df = get_all_investor_summary(start_date)  # pages=2 by default in function

if not investor_df.empty:
    summary_df = summary_df.merge(investor_df, on="sector", how="left")
    summary_df["inst_total"] = summary_df["inst_total"].fillna(0).astype(int)
    summary_df["frgn_total"] = summary_df["frgn_total"].fillna(0).astype(int)
    summary_df["inst_recent_5d"] = summary_df["inst_recent_5d"].fillna(0).astype(int)
    summary_df["frgn_recent_5d"] = summary_df["frgn_recent_5d"].fillna(0).astype(int)


# === 의견 판단 로직 ===
def judge_opinion(row):
    returns = row.get("returns_pct", 0)
    value_chg = row.get("value_change_pct", 0)
    inst = row.get("inst_total", 0)
    frgn = row.get("frgn_total", 0)
    inst_5d = row.get("inst_recent_5d", 0)
    frgn_5d = row.get("frgn_recent_5d", 0)

    smart_money_in = inst > 0 and frgn > 0
    smart_money_recent = inst_5d > 0 and frgn_5d > 0
    smart_money_out = inst < 0 and frgn < 0

    # 스마트머니 유입 + 아직 안 오름 = 최고 시그널
    if smart_money_in and returns < 15:
        return "🟢 스마트머니 유입 (초기)"
    if smart_money_in and value_chg > 30:
        return "🟢 스마트머니 몰리는 중"
    # 최근 5일 기관+외국인 동시 매수 = 단기 관심
    if smart_money_recent and not smart_money_in:
        return "🔵 단기 관심 급증"
    # 거래대금 급증인데 기관 매도 = 개인 주도
    if value_chg > 50 and inst < 0:
        return "🟡 개인 주도 상승 (주의)"
    # 많이 올랐고 스마트머니 빠짐 = 차익실현
    if returns > 40 and smart_money_out:
        return "🔴 과열·차익실현 주의"
    if smart_money_out:
        return "🔴 스마트머니 이탈"
    if smart_money_in:
        return "🟢 기관·외국인 순매수"
    return "⚪ 중립"


summary_df["opinion"] = summary_df.apply(judge_opinion, axis=1)

# 기본 정렬: 거래대금 변화 높은 순
summary_df = summary_df.sort_values("value_change_pct", ascending=False).reset_index(drop=True)

# === 1. 섹터 수익률 랭킹 ===
st.subheader(f"📊 섹터 ETF 자금 유입 랭킹 ({period})")
st.caption("거래대금 급증 = 돈이 몰리는 중 / 기관·외국인 순매수 = 스마트머니 / 의견으로 한눈에 판단")

base_cols = ["sector", "opinion", "etf_name", "returns_pct", "value_change_pct"]
rename_map = {
    "sector": "섹터", "opinion": "의견", "etf_name": "ETF",
    "returns_pct": f"수익률({period})",
    "value_change_pct": f"거래대금변화({period})",
}

if "inst_total" in summary_df.columns:
    base_cols += ["inst_total", "frgn_total", "inst_recent_5d", "frgn_recent_5d"]
    rename_map.update({
        "inst_total": f"기관순매수({period})",
        "frgn_total": f"외국인순매수({period})",
        "inst_recent_5d": "기관순매수(5일)",
        "frgn_recent_5d": "외국인순매수(5일)",
    })

display_df = summary_df[base_cols].rename(columns=rename_map)

# 리포트 집중도 합치기
if not report_sector_df.empty:
    sector_report_map = {}
    for _, row in report_sector_df.iterrows():
        sector_report_map[row["sector"]] = row["report_count"]

    display_df["리포트수"] = display_df["섹터"].map(
        lambda s: max([v for k, v in sector_report_map.items() if s in k or k in s], default=0)
    )
else:
    display_df["리포트수"] = 0

sector_selection = st.dataframe(
    display_df,
    use_container_width=True, hide_index=True,
    on_select="rerun", selection_mode="single-row",
    column_config={
        f"수익률({period})": st.column_config.NumberColumn(format="%.1f%%"),
        f"거래대금변화({period})": st.column_config.NumberColumn(format="%+.1f%%", help=f"{period} 전 초기5일 평균 거래대금 대비 최근5일 평균 변화"),
        f"기관순매수({period})": st.column_config.NumberColumn(format="%,d주", help="기간 내 기관 누적 순매수량"),
        f"외국인순매수({period})": st.column_config.NumberColumn(format="%,d주", help="기간 내 외국인 누적 순매수량"),
        "기관순매수(5일)": st.column_config.NumberColumn(format="%,d주"),
        "외국인순매수(5일)": st.column_config.NumberColumn(format="%,d주"),
    },
)

# === 2. 섹터 상세 차트 ===
st.divider()

if sector_selection and sector_selection.selection and sector_selection.selection.rows:
    sel_idx = sector_selection.selection.rows[0]
    sel_sector = summary_df.iloc[sel_idx]["sector"]
    sel_info = summary_df.iloc[sel_idx]

    st.subheader(f"📈 {sel_sector} — {sel_info['etf_name']} 상세")

    etf_df = get_etf_price(sel_info["etf_code"], start_date, end_date)

    if not etf_df.empty:
        etf_df["value"] = etf_df["close"] * etf_df["volume"]

        # 기관/외국인 매매동향 가져오기
        inv_df = get_investor_trading(sel_info["etf_code"], pages=5)

        has_inv = not inv_df.empty
        n_rows = 3 if has_inv else 2
        heights = [0.4, 0.3, 0.3] if has_inv else [0.6, 0.4]
        subtitles = [f"{sel_info['etf_name']} 가격 추이", "일별 거래대금"]
        if has_inv:
            subtitles.append("기관/외국인 순매수")

        fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True,
                            row_heights=heights, vertical_spacing=0.06,
                            subplot_titles=subtitles)

        fig.add_trace(go.Scatter(
            x=etf_df["date"], y=etf_df["close"],
            mode="lines", line=dict(color="royalblue", width=2),
            fill="tozeroy", fillcolor="rgba(65, 105, 225, 0.1)",
            name="ETF 가격",
            hovertemplate="%{x}<br>가격: %{y:,}원<extra></extra>",
        ), row=1, col=1)

        colors = ["rgba(34,197,94,0.6)" if v > etf_df["value"].mean() else "rgba(200,200,200,0.4)"
                  for v in etf_df["value"]]
        fig.add_trace(go.Bar(
            x=etf_df["date"], y=etf_df["value"],
            marker_color=colors, name="거래대금",
            hovertemplate="%{x}<br>거래대금: %{y:,.0f}원<extra></extra>",
        ), row=2, col=1)

        if has_inv:
            inv_colors_inst = ["rgba(255,59,48,0.7)" if v >= 0 else "rgba(59,130,246,0.7)" for v in inv_df["institution"]]
            fig.add_trace(go.Bar(
                x=inv_df["date"], y=inv_df["institution"],
                marker_color=inv_colors_inst, name="기관",
                hovertemplate="%{x}<br>기관: %{y:,}주<extra></extra>",
            ), row=3, col=1)
            fig.add_trace(go.Bar(
                x=inv_df["date"], y=inv_df["foreign"],
                marker_color="rgba(251,191,36,0.7)", name="외국인",
                hovertemplate="%{x}<br>외국인: %{y:,}주<extra></extra>",
            ), row=3, col=1)

        fig.update_layout(height=750 if has_inv else 600, showlegend=has_inv,
                          legend=dict(orientation="h", y=-0.05) if has_inv else {})
        fig.update_yaxes(tickformat=",", row=1, col=1)
        fig.update_yaxes(tickformat=",", row=2, col=1)
        if has_inv:
            fig.update_yaxes(tickformat=",", row=3, col=1)

        st.plotly_chart(fig, use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"수익률 ({period})", f"{sel_info['returns_pct']:+.1f}%")
        c2.metric("거래대금 변화", f"{sel_info['value_change_pct']:+.1f}%")
        if "inst_total" in sel_info:
            c3.metric(f"기관 순매수", f"{sel_info['inst_total']:+,}주")
            c4.metric(f"외국인 순매수", f"{sel_info['frgn_total']:+,}주")

    # === 해당 섹터의 리포트 DB 종목 리스트 + 덜 오른 종목 찾기 ===
    st.markdown(f"#### 🎯 {sel_sector} 섹터에서 아직 덜 오른 종목 찾기")
    st.caption(f"섹터 ETF는 {period} 동안 {sel_info['returns_pct']:+.1f}% — 이 안에서 덜 오른 종목 = 따라갈 여지")
    report_sectors = SECTOR_TO_REPORT.get(sel_sector, [])

    if has_report_db and report_sectors:
        try:
            import sqlite3
            from sector_lib.stock_price import get_return_and_current
            conn = sqlite3.connect(report_db_path)
            placeholders = ",".join("?" * len(report_sectors))
            stocks_df = pd.read_sql_query(
                f"""SELECT stock_name,
                       MAX(stock_code) as stock_code,
                       sector,
                       COUNT(*) as report_count,
                       COUNT(DISTINCT broker) as brokers,
                       MAX(report_date) as last_report
                    FROM reports
                    WHERE sector IN ({placeholders}) AND report_date >= ? AND target_price IS NOT NULL
                    GROUP BY stock_name
                    ORDER BY report_count DESC""",
                conn, params=report_sectors + [start_date],
            )

            # 각 종목 최근 목표가
            latest_targets = {}
            for name in stocks_df["stock_name"]:
                tp = conn.execute(
                    "SELECT target_price FROM reports WHERE stock_name=? AND target_price IS NOT NULL ORDER BY report_date DESC LIMIT 1",
                    (name,),
                ).fetchone()
                latest_targets[name] = tp[0] if tp else None
            conn.close()

            if not stocks_df.empty:
                with st.spinner(f"{len(stocks_df)}개 종목 주가 조회 중..."):
                    returns_list, current_list, upside_list = [], [], []
                    for _, r in stocks_df.iterrows():
                        code = r["stock_code"]
                        ret, cur = get_return_and_current(code, start_date, end_date) if code else (None, None)
                        target = latest_targets.get(r["stock_name"])
                        upside = round((target - cur) / cur * 100, 1) if (target and cur and cur > 0) else None
                        returns_list.append(ret)
                        current_list.append(cur)
                        upside_list.append(upside)

                    stocks_df["returns_pct"] = returns_list
                    stocks_df["current_price"] = current_list
                    stocks_df["latest_target"] = stocks_df["stock_name"].map(latest_targets)
                    stocks_df["upside_pct"] = upside_list

                # 괴리율 큰 순 (가장 덜 오른 순) 정렬
                stocks_df = stocks_df.sort_values("upside_pct", ascending=False, na_position="last")

                sector_etf_return = sel_info["returns_pct"]

                st.caption(f"리포트 DB 연동: {', '.join(report_sectors)} ({len(stocks_df)}개 종목) · 괴리율 큰 순 = 덜 오른 순")
                disp = stocks_df[[
                    "stock_name", "report_count", "brokers",
                    "returns_pct", "current_price", "latest_target", "upside_pct", "last_report"
                ]].rename(columns={
                    "stock_name": "종목", "report_count": "리포트수", "brokers": "증권사수",
                    "returns_pct": f"종목수익률({period})", "current_price": "현재가",
                    "latest_target": "목표가", "upside_pct": "괴리율(상승여력)",
                    "last_report": "최근리포트",
                })

                stock_sel = st.dataframe(
                    disp, use_container_width=True, hide_index=True,
                    on_select="rerun", selection_mode="single-row",
                    column_config={
                        f"종목수익률({period})": st.column_config.NumberColumn(format="%.1f%%", help=f"섹터ETF는 {sector_etf_return:+.1f}%"),
                        "현재가": st.column_config.NumberColumn(format="%,d원"),
                        "목표가": st.column_config.NumberColumn(format="%,d원"),
                        "괴리율(상승여력)": st.column_config.NumberColumn(format="%+.1f%%", help="목표가 대비 현재가 차이 — 클수록 덜 오른 종목"),
                    },
                )
                st.caption(f"💡 섹터ETF 수익률({sector_etf_return:+.1f}%)보다 종목수익률이 낮으면서 괴리율이 큰 종목 = 아직 덜 오른 기회")

                # 선택한 종목 → 관심종목 바로 추가
                if stock_sel and stock_sel.selection and stock_sel.selection.rows:
                    picked_idx = stock_sel.selection.rows[0]
                    picked = stocks_df.iloc[picked_idx]
                    picked_name = picked["stock_name"]
                    picked_code = picked["stock_code"]

                    already = any(it["stock_name"] == picked_name for it in wl.load_watchlist())
                    col_a, col_b = st.columns([3, 1])
                    col_a.markdown(f"**선택: {picked_name}** (괴리율 {picked['upside_pct']:+.1f}%)" if picked["upside_pct"] is not None else f"**선택: {picked_name}**")
                    if already:
                        col_b.success("✅ 이미 관심종목")
                    else:
                        if col_b.button(f"⭐ 관심종목 추가", key=f"add_{picked_name}", use_container_width=True):
                            wl.add_stock(picked_name, picked_code)
                            st.success(f"{picked_name} 관심종목 추가됨!")
                            st.rerun()
            else:
                st.info(f"{sel_sector} 섹터에 해당 기간 리포트가 없습니다.")
        except Exception as e:
            st.warning(f"종목 리스트 로드 실패: {e}")
    elif not report_sectors:
        st.info(f"{sel_sector} 섹터는 리포트 DB 매핑이 없습니다.")
    else:
        st.info("리포트 DB가 연결되지 않았습니다.")

else:
    st.info("👆 위 테이블에서 섹터를 클릭하면 상세 차트를 볼 수 있습니다.")

# === 3. 네이버 업종 전체 등락률 ===
st.divider()
st.subheader("📋 네이버 전체 업종 등락률 (오늘)")

rankings = get_sector_rankings()
if not rankings.empty:
    st.dataframe(
        rankings.rename(columns={
            "sector": "업종", "change_pct": "등락률", "stock_count": "종목수",
        })[["업종", "등락률", "종목수"]],
        use_container_width=True, hide_index=True,
    )
