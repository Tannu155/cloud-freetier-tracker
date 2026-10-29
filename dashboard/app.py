"""Streamlit dashboard for the Free Tier Tracker.

Run locally:   streamlit run dashboard/app.py
Free hosting:  Streamlit Community Cloud -> point it at this file.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB = Path(__file__).resolve().parent.parent / "data" / "usage.db"
ICON = {"OK": "🟢", "WARN": "🟡", "CRITICAL": "🟠", "OVER": "🔴"}

st.set_page_config(page_title="Free Tier Tracker", page_icon="☁️", layout="wide")
st.title("☁️ Multi-Cloud Free Tier Tracker")


@st.cache_data(ttl=300)
def load(path: str) -> pd.DataFrame:
    with sqlite3.connect(path) as conn:
        df = pd.read_sql("SELECT * FROM usage", conn)
    df["day"] = pd.to_datetime(df["day"])
    return df


if not DB.exists():
    st.warning("No data yet. Run `python -m tracker seed --days 30` or `python -m tracker run` first.")
    st.stop()

df = load(str(DB))
if df.empty:
    st.warning("Database is empty. Run the tracker first.")
    st.stop()

latest_day = df["day"].max()
st.caption(f"Last updated: {latest_day:%d %b %Y} · data from GitHub Actions daily run")

providers = sorted(df["provider"].unique())
chosen = st.multiselect("Clouds", providers, default=providers)
latest = df[(df["day"] == latest_day) & (df["provider"].isin(chosen))].sort_values("percent", ascending=False)

# ---- headline numbers ----
cols = st.columns(4)
for col, status in zip(cols, ["OK", "WARN", "CRITICAL", "OVER"]):
    col.metric(f"{ICON[status]} {status}", int((latest["status"] == status).sum()))

# ---- usage bars ----
st.subheader("Current usage")
for _, row in latest.iterrows():
    limit = row["limit_value"]
    label = (f"{ICON.get(row['status'], '⚪')} **{row['provider']}** · {row['service']} · {row['metric']} — "
             f"{row['used']:,.2f} / {limit:,.2f} {row['unit']} ({row['percent']:.0f}%)")
    if pd.notna(row["limit_date"]):
        label += f" · ⏰ limit around {pd.to_datetime(row['limit_date']):%d %b}"
    elif pd.notna(row["projected"]) and limit > 0 and row["projected"] > limit:
        label += f" · 📈 projected {row['projected']:,.0f}"
    st.progress(min(float(row["percent"]) / 100, 1.0), text=label)

# ---- history chart ----
st.subheader("History")
latest = latest.assign(label=latest["provider"] + " · " + latest["service"] + " · " + latest["metric"])
if not latest.empty:
    pick = st.selectbox("Metric", latest["label"].tolist())
    p, s, m = pick.split(" · ", 2)
    hist = df[(df["provider"] == p) & (df["service"] == s) & (df["metric"] == m)].sort_values("day")
    chart = hist.set_index("day")[["used", "limit_value"]].rename(columns={"limit_value": "free limit"})
    st.line_chart(chart)

with st.expander("Raw data"):
    st.dataframe(df.sort_values(["day", "provider"], ascending=[False, True]))
