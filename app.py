# app.py
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

DATABASE_NAME = "baby_log.db"

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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO baby_events (timestamp, event) VALUES (?, ?)", (now, event))
    conn.commit()
    conn.close()
    st.success(f"Logged: {event} at {now}")

def load_data():
    conn = sqlite3.connect(DATABASE_NAME)
    df = pd.read_sql_query("SELECT * FROM baby_events ORDER BY timestamp DESC", conn)
    conn.close()
    return df

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

    st.subheader("Event Log")
    df = load_data()
    st.dataframe(df)

if __name__ == "__main__":
    main()