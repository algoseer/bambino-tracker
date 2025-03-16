# app.py
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, date
import pytz
import time

DATABASE_NAME = "baby_log.db"
PDT = pytz.timezone('US/Pacific')

def create_table():
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS baby_events (
            timestamp TEXT,
            event TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_event(event):
    now_utc = datetime.utcnow()
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO baby_events (timestamp, event) VALUES (?, ?)", (now_str, event))
    conn.commit()
    conn.close()
    st.success(f"Logged: {event} at {now_utc.astimezone(PDT).strftime('%Y-%m-%d %H:%M:%S')} PDT")

def load_data(start_date):
    conn = sqlite3.connect(DATABASE_NAME)
    df = pd.read_sql_query("SELECT * FROM baby_events ORDER BY timestamp DESC", conn)
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert(PDT)
    df = df[df['timestamp'].dt.date >= start_date]
    df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    return df

def time_since_last(df, event_type, start_date):
    filtered_df = df[pd.to_datetime(df['timestamp']).dt.date >= start_date]
    last_event = filtered_df[filtered_df['event'] == event_type]['timestamp'].max()

    if pd.isnull(last_event):
        return "N/A"
    else:
        last_event_dt = datetime.strptime(last_event, '%Y-%m-%d %H:%M:%S').replace(tzinfo=PDT)
        now_pdt = datetime.now(PDT)
        last_event_epoch = int(last_event_dt.timestamp())
        now_pdt_epoch = int(now_pdt.timestamp())
        time_diff_seconds = now_pdt_epoch - last_event_epoch
        # st.markdown(last_event_dt)
        # st.markdown(now_pdt)
        time_diff = timedelta(seconds=time_diff_seconds)
        return str(time_diff)

def main():
    st.title("👶 Baby Tracking App")

    create_table()

    yesterday = date.today() - timedelta(days=1)
    start_date = st.sidebar.date_input("Show events from:", yesterday)

    if st.sidebar.button("Breastfeeding"):
        log_event("Breastfeeding")

    poop_pee_options = ["Pee", "Poop"]
    poop_pee_selection = st.sidebar.segmented_control("",poop_pee_options,selection_mode = "multi", default=["Poop"])

    if st.sidebar.button("Diaper Change"):
        log_event("Diaper Change")
        if "Pee" in poop_pee_selection:
            log_event("Pee")
        if "Poop" in poop_pee_selection:
            log_event("Poop")

    if st.sidebar.button("Mom Painmeds"):
        log_event("Mom Painmeds")

    st.subheader("Event Log")
    df = load_data(start_date)

    # Current Time Clock
    now_pdt = datetime.now(PDT).strftime("%Y-%m-%d %H:%M:%S %Z")
    st.metric("**Current Time (PDT):**", now_pdt)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Time since last diaper change", time_since_last(df, "Diaper Change", start_date))
    with col2:
        st.metric("Time since last feeding", time_since_last(df, "Breastfeeding", start_date))
    with col3:
        st.metric("Time since last pain med", time_since_last(df, "Mom Painmeds", start_date))

    st.dataframe(df)

if __name__ == "__main__":
    main()