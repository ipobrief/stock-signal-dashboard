import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from signal_lib.db import init_db, get_reports, get_sectors, get_report_count
from signal_lib.analysis import compute_signals, compute_leading_signals, get_stock_target_history
from signal_lib.stock_price import get_stock_price
from shared import watchlist as wl

st.set_page_config(page_title="애널리스트 시그널", page_icon="🎯", layout="wide")
init_db()


@st.dialog("💻 데이터 갱신은 내 PC에서 해주세요")
def show_local_only_dialog():
    st.markdown("""
**클라우드(웹)에서는 크롤링한 데이터가 저장되지 않습니다.**
(앱이 재시작되면 사라지고, 공개 앱에도 반영되지 않습니다)

데이터를 영구적으로 갱신하려면 **내 컴퓨터**에서:

👉 `stock-dashboard` 폴더의 **`데이터_갱신.bat`** 를 **더블클릭**하세요.

→ 크롤링 + GitHub 푸시가 자동으로 진행되고,
   1~2분 후 이 공개 앱에도 반영됩니다. (화면 띄울 필요 없음)
""")
    if st.button("확인", use_container_width=True):
        st.rerun()


st.title("🎯 애널리스트 시그널")

# --- Sidebar ---
with st.sidebar:
    st.header("설정")

    st.subheader("데이터 수집")
    from shared import gitsync
    is_local = gitsync.is_local()

    crawl_pages = st.slider("크롤링 페이지 수", 10, 500, 200)

    # 자동 푸시 체크박스는 로컬에서만 표시
    auto_push = False
    if is_local:
        auto_push = st.checkbox("크롤링 후 GitHub 자동 푸시 (클라우드 갱신)",
                                value=True,
                                help="크롤링한 데이터를 GitHub에 올려 공개 앱을 갱신합니다.")

    if st.button("📡 네이버 크롤링 시작", use_container_width=True):
        if not is_local:
            # 클라우드에서는 크롤링 대신 안내 팝업
            show_local_only_dialog()
        else:
            with st.spinner(f"{crawl_pages}페이지 크롤링 중..."):
                from signal_lib.crawlers.naver import crawl_naver
                progress = st.progress(0)
                def naver_progress(page, total):
                    progress.progress(page / total)
                count = crawl_naver(max_pages=crawl_pages, progress_callback=naver_progress)
                progress.empty()
            st.success(f"{count}건 신규 수집!")

            if auto_push:
                with st.spinner("GitHub에 데이터 푸시 중..."):
                    ok, msg = gitsync.push_data(f"데이터 갱신: 리포트 {count}건 신규 수집")
                if ok:
                    st.success(f"☁️ {msg}")
                else:
                    st.info(f"ℹ️ {msg}")
            st.rerun()

    st.divider()
    report_count = get_report_count()
    st.metric("총 리포트 수", f"{report_count:,}건")

    st.subheader("필터")
    min_reports = st.slider("최소 리포트 수", 3, 30, 5)
    all_sectors = get_sectors()
    selected_sectors = st.multiselect("업종 필터", all_sectors, default=[])

# --- Load Data ---
df_all = get_reports()

if df_all.empty:
    st.info("데이터가 없습니다. 사이드바에서 크롤링을 실행해주세요.")
    st.stop()

data_min = pd.to_datetime(df_all["report_date"]).min().date()
data_max = pd.to_datetime(df_all["report_date"]).max().date()
default_start = max(data_min, data_max - timedelta(days=90))

with st.sidebar:
    st.subheader("분석 기간")
    start_date = st.date_input("시작일", value=default_start, min_value=data_min, max_value=data_max)

df = df_all[pd.to_datetime(df_all["report_date"]).dt.date >= start_date].copy()

if df.empty:
    st.info("선택한 기간에 데이터가 없습니다.")
    st.stop()

date_range = f"{start_date} ~ {data_max}"
stock_count = df["stock_name"].nunique()
st.caption(f"📊 {stock_count}개 종목 / {len(df):,}건 리포트 ({date_range})")

def render_detail_chart(stock_name, stock_code, df_all, info_dict=None):
    # 관심종목 추가 버튼
    col_w1, col_w2 = st.columns([3, 1])
    if wl.is_in_watchlist(stock_name):
        col_w2.success("⭐ 관심종목 등록됨")
    else:
        if col_w2.button("⭐ 관심종목 추가", key=f"wl_{stock_name}", use_container_width=True):
            wl.add_stock(stock_name, stock_code)
            st.success(f"{stock_name} 관심종목 추가됨!")
            st.rerun()

    history = get_stock_target_history(df_all, stock_name)
    if history.empty:
        st.warning("리포트 데이터가 없습니다.")
        return

    first_dt = history["report_date"].min().strftime("%Y-%m-%d")
    last_dt = history["report_date"].max().strftime("%Y-%m-%d")

    price_df = pd.DataFrame()
    if stock_code:
        price_df = get_stock_price(stock_code, first_dt, last_dt)

    fig = go.Figure()

    if not price_df.empty:
        fig.add_trace(go.Scatter(
            x=price_df["date"], y=price_df["close"],
            mode="lines", line=dict(color="rgba(34, 197, 94, 0.8)", width=1.5),
            fill="tozeroy", fillcolor="rgba(34, 197, 94, 0.1)",
            name="실제 주가",
            hovertemplate="주가: %{y:,}원<extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=history["report_date"], y=history["target_price"],
        mode="markers", marker=dict(size=10, color="royalblue", opacity=0.7),
        text=history["broker"], name="목표가",
        hovertemplate="<b>%{text}</b><br>날짜: %{x}<br>목표가: %{y:,}원<extra></extra>",
    ))

    history_sorted = history.sort_values("report_date")
    if len(history_sorted) >= 3:
        history_sorted["ma"] = history_sorted["target_price"].rolling(3, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=history_sorted["report_date"], y=history_sorted["ma"],
            mode="lines", line=dict(color="red", width=2),
            name="목표가 이동평균",
        ))

    title = f"{stock_name} — 목표가 vs 실제 주가"
    fig.update_layout(
        title=title, xaxis_title="날짜", yaxis_title="가격 (원)",
        height=550, yaxis=dict(tickformat=","),
        showlegend=True, legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Upside calculation
    if not price_df.empty and info_dict and info_dict.get("latest_target"):
        current_price = int(price_df.iloc[-1]["close"])
        latest_target = info_dict["latest_target"]
        upside = round((latest_target - current_price) / current_price * 100, 1)
        c1, c2, c3 = st.columns(3)
        c1.metric("현재 주가", f"{current_price:,}원")
        c2.metric("최근 목표가", f"{latest_target:,}원")
        c3.metric("괴리율 (상승여력)", f"{upside:+.1f}%")

    st.caption(f"총 {len(history)}건의 리포트")
    history_display = history.copy()
    if "report_url" in history_display.columns:
        history_display["리포트 제목"] = history_display.apply(
            lambda r: f"[{r['title']}]({r['report_url']})" if pd.notna(r.get("report_url")) and r.get("report_url") else r["title"],
            axis=1,
        )
    else:
        history_display["리포트 제목"] = history_display["title"]

    st.dataframe(
        history_display[["report_date", "broker", "리포트 제목", "target_price", "opinion"]].rename(columns={
            "report_date": "날짜", "broker": "증권사", "target_price": "목표가", "opinion": "투자의견",
        }),
        use_container_width=True, hide_index=True,
        column_config={
            "목표가": st.column_config.NumberColumn(format="%,d원"),
            "리포트 제목": st.column_config.LinkColumn(display_text=".*\\[(.+?)\\].*"),
        },
    )


def render_sector_peers(sel_sector, df_all, signal_names_set=None):
    """같은 섹터 전체 종목 비교 테이블"""
    sector_all = df_all[df_all["sector"] == sel_sector]
    if sector_all.empty:
        return
    peers = sector_all.groupby("stock_name").agg(
        stock_code=("stock_code", "first"),
        report_count=("id", "count"),
        brokers=("broker", "nunique"),
        latest_target=("target_price", lambda x: int(x.dropna().iloc[-1]) if not x.dropna().empty else None),
    ).reset_index().sort_values("report_count", ascending=False)
    peers_disp = peers.rename(columns={
        "stock_name": "종목", "report_count": "리포트수", "brokers": "증권사수", "latest_target": "최근목표가",
    })
    st.markdown(f"##### 📋 {sel_sector} — 같은 섹터 종목")
    st.dataframe(
        peers_disp[["종목", "리포트수", "증권사수", "최근목표가"]],
        use_container_width=True, hide_index=True,
        column_config={"최근목표가": st.column_config.NumberColumn(format="%,d원")},
    )


# --- 관심종목 현황 ---
watch_items = wl.load_watchlist()
with st.expander(f"⭐ 관심종목 ({len(watch_items)}개)", expanded=bool(watch_items)):
    if not watch_items:
        st.caption("아직 관심종목이 없습니다. 종목 상세에서 '⭐ 관심종목 추가'를 눌러보세요.")
    else:
        def _latest_target(name):
            sub = df[(df["stock_name"] == name) & (df["target_price"].notna())]
            if sub.empty:
                return None
            return int(sub.sort_values("report_date").iloc[-1]["target_price"])

        rows = []
        for it in watch_items:
            name = it["stock_name"]
            code = it.get("stock_code")
            target = _latest_target(name)
            cur = None
            if code:
                pdf = get_stock_price(code, start_date.strftime("%Y-%m-%d"), data_max.strftime("%Y-%m-%d"))
                if not pdf.empty:
                    cur = int(pdf.iloc[-1]["close"])
            upside = round((target - cur) / cur * 100, 1) if (target and cur and cur > 0) else None
            rows.append({"종목": name, "현재가": cur, "목표가": target, "괴리율(상승여력)": upside})

        watch_df = pd.DataFrame(rows).sort_values("괴리율(상승여력)", ascending=False, na_position="last").reset_index(drop=True)
        watch_sel = st.dataframe(
            watch_df, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "현재가": st.column_config.NumberColumn(format="%,d원"),
                "목표가": st.column_config.NumberColumn(format="%,d원"),
                "괴리율(상승여력)": st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )
        st.caption("👆 관심종목을 클릭하면 아래에 목표가 변화 상세 + 같은 섹터 종목이 열립니다.")
        rm = st.selectbox("관심종목 삭제", [""] + [it["stock_name"] for it in watch_items], key="wl_remove")
        if st.button("🗑️ 삭제") and rm:
            wl.remove_stock(rm)
            st.rerun()

        # 관심종목 선택 시 상세 연동
        if watch_sel and watch_sel.selection and watch_sel.selection.rows:
            wi = watch_sel.selection.rows[0]
            w_name = watch_df.iloc[wi]["종목"]
            w_item = next((it for it in watch_items if it["stock_name"] == w_name), None)
            w_code = w_item.get("stock_code") if w_item else None
            w_sector_sub = df[df["stock_name"] == w_name]["sector"]
            w_sector = w_sector_sub.iloc[0] if not w_sector_sub.empty else None
            w_target = _latest_target(w_name)

            st.divider()
            st.markdown(f"### 📈 {w_name} — 목표가 변화 상세")
            render_detail_chart(w_name, w_code, df, {"latest_target": w_target})
            if w_sector:
                render_sector_peers(w_sector, df)

# --- Tabs ---
tab_leading, tab_trend = st.tabs(["⚡ 선행 시그널 (아직 안 움직인 종목)", "📈 추세 시그널 (이미 움직이는 종목)"])


# ==========================================
# TAB 1: 선행 시그널
# ==========================================
with tab_leading:
    st.subheader("⚡ 애널리스트는 알고 있지만 주가는 아직 안 움직인 종목")
    st.caption("관심도 급증 + 신규 커버리지 + 목표가 상향 → 종목 클릭 시 현재 주가 대비 괴리율 확인")

    leading_df = compute_leading_signals(df, min_reports=min_reports)

    if leading_df.empty:
        st.warning("선행 시그널 종목이 없습니다.")
    else:
        # --- 핫 섹터 ---
        sector_signal_counts = leading_df.groupby("sector").agg(
            signal_count=("stock_name", "count"),
            avg_score=("score", "mean"),
            top_stock=("stock_name", "first"),
        ).sort_values("signal_count", ascending=False)
        sector_signal_counts = sector_signal_counts[sector_signal_counts["signal_count"] >= 2]

        if not sector_signal_counts.empty:
            st.markdown("### 🔥 핫 섹터")
            st.caption("시그널 종목이 2개 이상 몰린 업종 — 섹터 클릭 시 해당 업종 전체 종목 비교")

            hot_sectors_display = sector_signal_counts.reset_index().rename(columns={
                "sector": "업종", "signal_count": "시그널종목수", "avg_score": "평균점수", "top_stock": "대표종목",
            })

            hot_selection = st.dataframe(
                hot_sectors_display,
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                column_config={
                    "평균점수": st.column_config.NumberColumn(format="%.0f점"),
                },
            )

            if hot_selection and hot_selection.selection and hot_selection.selection.rows:
                sel_sector_idx = hot_selection.selection.rows[0]
                sel_sector = hot_sectors_display.iloc[sel_sector_idx]["업종"]

                st.markdown(f"#### 📋 {sel_sector} — 전체 종목 비교")
                st.caption("✅ 감지 = 시그널 종목 / 빈칸 = 같은 섹터인데 아직 덜 움직인 종목 (기회)")

                sector_all = df[df["sector"] == sel_sector]
                sector_stocks = sector_all.groupby("stock_name").agg(
                    stock_code=("stock_code", "first"),
                    report_count=("id", "count"),
                    brokers=("broker", "nunique"),
                    latest_target=("target_price", lambda x: x.dropna().iloc[-1] if not x.dropna().empty else None),
                ).reset_index()

                signal_names = set(leading_df[leading_df["sector"] == sel_sector]["stock_name"])
                sector_stocks["시그널"] = sector_stocks["stock_name"].apply(lambda x: "✅ 감지" if x in signal_names else "")

                signal_scores = leading_df[["stock_name", "score", "attention_ratio", "tp_raises"]].copy()
                sector_stocks = sector_stocks.merge(signal_scores, on="stock_name", how="left")
                sector_stocks["score"] = sector_stocks["score"].fillna(0)
                sector_stocks["attention_ratio"] = sector_stocks["attention_ratio"].fillna(0)
                sector_stocks["tp_raises"] = sector_stocks["tp_raises"].fillna(0).astype(int)
                sector_stocks = sector_stocks.sort_values("시그널", ascending=False, key=lambda x: x != "")

                sector_display = sector_stocks.rename(columns={
                    "stock_name": "종목", "report_count": "리포트수", "brokers": "증권사수",
                    "latest_target": "최근목표가", "score": "점수",
                    "attention_ratio": "관심급증", "tp_raises": "목표가갱신",
                })

                sector_sel = st.dataframe(
                    sector_display[["시그널", "종목", "리포트수", "증권사수", "최근목표가", "관심급증", "목표가갱신", "점수"]],
                    use_container_width=True, hide_index=True,
                    on_select="rerun", selection_mode="single-row",
                    column_config={
                        "최근목표가": st.column_config.NumberColumn(format="%,d원"),
                        "관심급증": st.column_config.NumberColumn(format="%.1fx"),
                        "점수": st.column_config.NumberColumn(format="%.0f점"),
                    },
                )

                if sector_sel and sector_sel.selection and sector_sel.selection.rows:
                    sel_row = sector_sel.selection.rows[0]
                    sel_name = sector_display.iloc[sel_row]["종목"]
                    sel_code = sector_stocks.iloc[sel_row]["stock_code"]
                    st.subheader(f"📈 {sel_name} — 목표가 변화 상세")
                    render_detail_chart(sel_name, sel_code, df, {"latest_target": sector_stocks.iloc[sel_row]["latest_target"]})

            st.divider()

        if selected_sectors:
            leading_df = leading_df[leading_df["sector"].isin(selected_sectors)]

        only_tp_raises = st.toggle("🔄 목표가 갱신 종목만 보기", value=False,
                                    help="동일 증권사가 목표가를 상향 조정한 이력이 있는 종목만 표시")

        if only_tp_raises:
            leading_df = leading_df[leading_df["tp_raises"] >= 2]

        st.success(f"🔥 {len(leading_df)}개 종목 발견")

        lead_display = leading_df[[
            "stock_name", "sector", "latest_target",
            "tp_raises", "tp_raises_brokers",
            "recent_reports", "attention_ratio", "new_brokers", "total_brokers",
            "target_trending_up", "score"
        ]].rename(columns={
            "stock_name": "종목",
            "sector": "업종",
            "latest_target": "최근목표가",
            "tp_raises": "목표가갱신",
            "tp_raises_brokers": "갱신증권사",
            "recent_reports": "최근1개월",
            "attention_ratio": "관심급증",
            "new_brokers": "신규커버",
            "total_brokers": "총증권사",
            "target_trending_up": "목표가↑",
            "score": "점수",
        })

        lead_selection = st.dataframe(
            lead_display,
            use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "최근목표가": st.column_config.NumberColumn(format="%,d원"),
                "목표가갱신": st.column_config.NumberColumn(format="%d회", help="동일 증권사가 목표가를 상향한 횟수 (주가가 목표가에 닿아서 갱신)"),
                "갱신증권사": st.column_config.NumberColumn(format="%d곳", help="목표가를 상향 조정한 증권사 수"),
                "관심급증": st.column_config.NumberColumn(format="%.1fx", help="최근1개월 리포트 수 / 이전 월평균"),
                "신규커버": st.column_config.NumberColumn(help="최근1개월 새로 리포트 작성한 증권사 수"),
                "목표가↑": st.column_config.CheckboxColumn(),
                "점수": st.column_config.NumberColumn(format="%.0f점"),
            },
        )

        st.divider()

        if lead_selection and lead_selection.selection and lead_selection.selection.rows:
            row_idx = lead_selection.selection.rows[0]
            sel_name = lead_display.iloc[row_idx]["종목"]
            sel_code = leading_df.iloc[row_idx]["stock_code"]
            sel_info = leading_df.iloc[row_idx].to_dict()

            st.subheader(f"📈 {sel_name} — 목표가 변화 상세")

            if sel_info.get("new_broker_names"):
                st.caption(f"🆕 신규 커버리지: {sel_info['new_broker_names']}")

            render_detail_chart(sel_name, sel_code, df, sel_info)
        else:
            st.info("👆 위 테이블에서 종목을 클릭하면 현재 주가 대비 괴리율과 상세 차트를 볼 수 있습니다.")


# ==========================================
# TAB 2: 추세 시그널 (기존)
# ==========================================
with tab_trend:
    st.subheader("📈 리포트 꾸준 발간 + 목표가 점진 상향 종목")
    st.caption("이미 추세가 형성된 종목 (R>0 = 상향 추세 일관성)")

    signals_df = compute_signals(df, min_reports=min_reports)

    if signals_df.empty:
        st.warning("분석할 데이터가 부족합니다.")
    else:
        min_r = st.slider("최소 상관계수 (R)", 0.1, 0.9, 0.3, 0.05, key="trend_r")
        filtered = signals_df[signals_df["signal"]].copy()
        filtered = filtered[filtered["r_value"] >= min_r]
        if selected_sectors:
            filtered = filtered[filtered["sector"].isin(selected_sectors)]

        st.success(f"🚀 시그널 종목: {len(filtered)}개")

        display_df = filtered[[
            "stock_name", "stock_code", "sector", "total_reports", "unique_brokers",
            "avg_monthly_reports", "first_3_avg", "last_3_avg",
            "change_pct", "r_value", "first_date", "last_date"
        ]].rename(columns={
            "stock_name": "종목", "sector": "업종", "total_reports": "리포트수",
            "unique_brokers": "증권사수", "avg_monthly_reports": "월평균",
            "first_3_avg": "초기목표가", "last_3_avg": "최근목표가",
            "change_pct": "변화율(%)", "r_value": "R값",
            "first_date": "시작일", "last_date": "최근일",
        })

        trend_selection = st.dataframe(
            display_df.drop(columns=["stock_code"]),
            use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "변화율(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "초기목표가": st.column_config.NumberColumn(format="%,d원"),
                "최근목표가": st.column_config.NumberColumn(format="%,d원"),
            },
        )

        st.divider()

        if trend_selection and trend_selection.selection and trend_selection.selection.rows:
            row_idx = trend_selection.selection.rows[0]
            sel_name = display_df.iloc[row_idx]["종목"]
            sel_code = filtered.iloc[row_idx]["stock_code"]
            sel_info = filtered.iloc[row_idx].to_dict()
            st.subheader(f"📈 {sel_name} — 목표가 변화 상세")
            render_detail_chart(sel_name, sel_code, df, sel_info)
        else:
            st.info("👆 위 테이블에서 종목을 클릭하면 목표가 변화 상세를 볼 수 있습니다.")
