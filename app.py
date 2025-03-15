# app.py
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import pytz

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

def load_data():
    conn = sqlite3.connect(DATABASE_NAME)
    df = pd.read_sql_query("SELECT * FROM baby_events ORDER BY timestamp ASC", conn) # Sort ascending
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert(PDT) # Convert to PDT
    df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S') #reformat for display
    return df

def time_since_last(df, event_type):
    last_event = df[df['event'] == event_type]['timestamp'].max()
    if pd.isnull(last_event):
        return "N/A"
    else:
        last_event_dt = datetime.strptime(last_event, '%Y-%m-%d %H:%M:%S').replace(tzinfo=PDT)
        now_pdt = datetime.now(PDT)
        time_diff = now_pdt - last_event_dt
        return str(time_diff)

def main():
    st.title("Baby Tracking App")

    create_table()

    if st.sidebar.button("Breastfeeding"):
        log_event("Breastfeeding")
    if st.sidebar.button("Diaper Change"):
        log_event("Diaper Change")
    if st.sidebar.button("Pee"):
        log_event("Pee")
    if st.sidebar.button("Poop"):
        log_event("Poop")
    if st.sidebar.button("Mom Painmeds"):
        log_event("Mom Painmeds")

    st.subheader("Event Log")
    df = load_data()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Time since last diaper change", time_since_last(df, "Diaper Change"))
    with col2:
        st.metric("Time since last feeding", time_since_last(df, "Breastfeeding"))
    with col3:
        st.metric("Time since last pain med", time_since_last(df, "Mom Painmeds"))

    st.dataframe(df)

if __name__ == "__main__":
    main()