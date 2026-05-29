import pandas as pd
import numpy as np
from scipy import stats


def compute_signals(df: pd.DataFrame, min_reports: int = 5) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])

    results = []
    for stock_name, group in df.groupby("stock_name"):
        group = group.sort_values("report_date")
        prices = group["target_price"].dropna()
        if len(prices) < min_reports:
            continue

        x = np.arange(len(prices))
        slope, intercept, r, p, se = stats.linregress(x, prices)

        first_month_avg = prices.iloc[:3].mean()
        last_month_avg = prices.iloc[-3:].mean()
        change_pct = (
            (last_month_avg - first_month_avg) / first_month_avg * 100
            if first_month_avg > 0
            else 0
        )

        monthly = group.set_index("report_date").resample("MS").size()
        avg_monthly = monthly.mean()

        sector = group.iloc[0].get("sector", "기타")
        stock_code = group["stock_code"].dropna().iloc[0] if not group["stock_code"].dropna().empty else None
        total_reports = len(group)
        brokers = group["broker"].nunique()
        first_date = group["report_date"].min()
        last_date = group["report_date"].max()

        is_signal = slope > 0 and r > 0.3 and total_reports >= min_reports

        results.append({
            "stock_name": stock_name,
            "stock_code": stock_code,
            "sector": sector,
            "total_reports": total_reports,
            "unique_brokers": brokers,
            "avg_monthly_reports": round(avg_monthly, 1),
            "first_3_avg": int(first_month_avg),
            "last_3_avg": int(last_month_avg),
            "change_pct": round(change_pct, 1),
            "r_value": round(r, 2),
            "slope": round(slope, 1),
            "signal": is_signal,
            "first_date": first_date.strftime("%Y-%m-%d"),
            "last_date": last_date.strftime("%Y-%m-%d"),
        })

    result_df = pd.DataFrame(results)
    if result_df.empty:
        return result_df

    return result_df.sort_values("change_pct", ascending=False)


def compute_leading_signals(df: pd.DataFrame, min_reports: int = 3) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    now = df["report_date"].max()
    one_month_ago = now - pd.DateOffset(months=1)
    three_months_ago = now - pd.DateOffset(months=3)

    results = []
    for stock_name, group in df.groupby("stock_name"):
        group = group.sort_values("report_date")
        stock_code = group["stock_code"].dropna().iloc[0] if not group["stock_code"].dropna().empty else None
        if not stock_code:
            continue

        prices_all = group["target_price"].dropna()
        if len(prices_all) < min_reports:
            continue

        sector = group.iloc[0].get("sector", "기타")

        # 1. 관심도 급증
        recent = group[group["report_date"] >= one_month_ago]
        previous = group[(group["report_date"] >= three_months_ago) & (group["report_date"] < one_month_ago)]

        recent_count = len(recent)
        prev_monthly = len(previous) / 2 if len(previous) > 0 else 0
        attention_ratio = round(recent_count / prev_monthly, 1) if prev_monthly > 0 else (10.0 if recent_count > 0 else 0)

        # 2. 신규 커버리지
        recent_brokers = set(recent["broker"].unique())
        prev_brokers = set(previous["broker"].unique())
        new_brokers = recent_brokers - prev_brokers
        new_broker_count = len(new_brokers)
        total_brokers = group["broker"].nunique()

        # 3. 최근 목표가 방향
        recent_prices = prices_all.tail(5)
        if len(recent_prices) >= 3:
            x = np.arange(len(recent_prices))
            recent_slope, _, recent_r, _, _ = stats.linregress(x, recent_prices)
            target_trending_up = recent_slope > 0
        else:
            target_trending_up = False

        latest_target = int(prices_all.iloc[-1])

        # 4. 목표가 연속 상향 횟수 (동일 증권사가 목표가를 올린 횟수)
        tp_raises = 0
        tp_raises_brokers = set()
        for broker_name, broker_grp in group.groupby("broker"):
            broker_prices = broker_grp.sort_values("report_date")["target_price"].dropna()
            if len(broker_prices) < 2:
                continue
            vals = broker_prices.values
            for i in range(1, len(vals)):
                if vals[i] > vals[i - 1]:
                    tp_raises += 1
                    tp_raises_brokers.add(broker_name)

        # 복합 점수
        score = 0
        if attention_ratio >= 1.5:
            score += min(attention_ratio, 5) * 10
        if new_broker_count > 0:
            score += new_broker_count * 15
        if target_trending_up:
            score += 20
        if tp_raises >= 2:
            score += tp_raises * 10

        if score <= 0:
            continue

        results.append({
            "stock_name": stock_name,
            "stock_code": stock_code,
            "sector": sector,
            "latest_target": latest_target,
            "recent_reports": recent_count,
            "prev_monthly_avg": round(prev_monthly, 1),
            "attention_ratio": attention_ratio,
            "new_brokers": new_broker_count,
            "tp_raises": tp_raises,
            "tp_raises_brokers": len(tp_raises_brokers),
            "new_broker_names": ", ".join(new_brokers) if new_brokers else "",
            "total_brokers": total_brokers,
            "target_trending_up": target_trending_up,
            "score": round(score, 1),
        })

    result_df = pd.DataFrame(results)
    if result_df.empty:
        return result_df

    return result_df.sort_values("score", ascending=False)


def get_stock_target_history(df: pd.DataFrame, stock_name: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    stock_df = df[df["stock_name"] == stock_name].sort_values("report_date")

    if stock_df.empty:
        return pd.DataFrame()

    cols = ["report_date", "broker", "title", "target_price", "opinion"]
    if "report_url" in stock_df.columns:
        cols.append("report_url")
    return stock_df[cols].reset_index(drop=True)
