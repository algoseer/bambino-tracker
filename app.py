# app.py
import streamlit as st
import sqlite3
import time
import pandas as pd
from functools import partial
from datetime import datetime, timedelta, date
import pytz
import plotly.graph_objects as go

DATABASE_NAME = "baby_log.db"
PDT = pytz.timezone('US/Pacific')

def create_table(dbname=DATABASE_NAME):
    conn = sqlite3.connect(dbname)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS baby_events (
            timestamp TEXT,
            event TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_event(event, comments=""):
    now_utc = datetime.utcnow()
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    if comments:
        event=f"{event}+{comments}"
    c.execute("INSERT INTO baby_events (timestamp, event) VALUES (?, ?)", (now_str, event))
    conn.commit()
    conn.close()
    st.success(f"Logged: {event} at {now_utc.astimezone(PDT).strftime('%Y-%m-%d %H:%M:%S')} PDT")

def extract_comment(s, idx=1):
    if isinstance(s, str) and '+' in s:
        try:
            return s.split('+')[idx]
        except IndexError:
            return "" # Handles cases where there's no element at index 1
    else:
        return s if idx==0 else None   # Handles non-string or no '+' cases


def load_data(start_date):
    conn = sqlite3.connect(DATABASE_NAME)
    df = pd.read_sql_query("SELECT rowid,timestamp, event FROM baby_events ORDER BY timestamp DESC", conn)
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert(PDT)
    df = df[df['timestamp'].dt.date >= start_date]
    df['date'] = df['timestamp'].dt.date
    df['time'] = df['timestamp'].dt.time

    df['comments'] = df['event'].apply(partial(extract_comment,idx=1))
    df['event'] = df['event'].apply(partial(extract_comment,idx=0))

    df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    return df

def time_since_last(df, event_type, start_date):

    filtered_df = df[pd.to_datetime(df['timestamp']).dt.date >= start_date] #this is in pdt
    last_event = filtered_df[filtered_df['event'].str.startswith(event_type)]['timestamp'].max()

    if pd.isnull(last_event):
        return "N/A"
    else:
        last_event_dt = PDT.localize(datetime.strptime(last_event, '%Y-%m-%d %H:%M:%S'))
        now_pdt = datetime.now(PDT)
        last_event_epoch = int(last_event_dt.timestamp())
        now_pdt_epoch = int(now_pdt.timestamp())
        time_diff_seconds = now_pdt_epoch - last_event_epoch
        time_diff = timedelta(seconds=time_diff_seconds)
        return str(time_diff)

def count_events(df, event_type, start_date):
    filtered_df = df[pd.to_datetime(df['timestamp']).dt.date >= start_date]
    count = len(filtered_df[filtered_df['event'].str.startswith(event_type)])
    return count

def update_logs(df_edited):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        for index, row in df_edited.iterrows():
            combined_datetime = PDT.localize(datetime.combine(row['date'], row['time']))
            combined_datetime_utc = combined_datetime.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
            if row['comments']:
                combined_event_comment = f"{row['event']}+{row['comments']}"
            else:
                combined_event_comment =  row["event"]

            c.execute("UPDATE baby_events SET timestamp = ?, event = ? WHERE rowid = ?", (combined_datetime_utc, combined_event_comment, row['rowid']))
        conn.commit()
        conn.close()
        st.success("Timestamps updated!")
    except ValueError:
        st.error("Invalid timestamp format.")

#Plot data that is showing in the table below on a radar plot
def create_radar_plot(df, timestamp_column='timestamp'):

    ## Filter only for events in the last 24 hrs.
    df_filtered = df.copy()
    ts = pd.to_datetime(df_filtered[timestamp_column]).dt.tz_localize(PDT)
    # Get the current time, and subtract 24 hours
    now = datetime.now(PDT)
    twenty_four_hours_ago = now - timedelta(hours=24)
    # Filter the DataFrame
    df_filtered = df_filtered[ts >= twenty_four_hours_ago]

    categories = ['Breastfeeding', 'Pee', 'Poop']
    colors = ['brown', 'blue', 'green']
    markers = ['circle-open-dot','square-open', 'x']
    fig = go.Figure()

    idx = 0.5
    date = df_filtered['date'].iloc[-1]
    for marker, category, color in zip(markers, categories, colors):
        filtered_events = df_filtered[df_filtered['event'].str.startswith(category)]
        times = [(t.hour + t.minute / 60)*360/24 for t in filtered_events['time']]
        comments = [a if a else "" for a in filtered_events['comments']]
        fig.add_trace(go.Scatterpolar(
            r=[idx] * len(times),
            theta=times,
            mode='markers',
            customdata=comments,
            marker=dict(symbol=marker,color=color, size=8),
            name=category,
            hovertemplate="%{customdata}<extra></extra>",
        ))
        idx+=0.2

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=False),
            angularaxis=dict(
                tickmode='array', 
                tickvals=list(range(0,360, 15)),
                ticktext=[f"{i:02d}:00" for i in range(24)],
                direction='clockwise',
                rotation=90,
            )
        ),
        title=f'Daily Activity for {date}',
    )
    return fig


def main():
    st.title("👶 Baby Tracking System 💜")
    create_table()

    yesterday = date.today() - timedelta(days=1)
    start_date = st.sidebar.date_input("Show events from:", yesterday)

    disable_push =  bool(int(st.query_params.get("viewonly", "0")))

    comments = st.sidebar.text_input("Comments")
    if st.sidebar.button("Breastfeeding",icon="🍼", disabled=disable_push):
        log_event("Breastfeeding", comments=comments)


    st.sidebar.divider()
    poop_pee_options = ["Pee", "Poop"]
    poop_pee_selection = st.sidebar.segmented_control("", poop_pee_options, selection_mode="multi", default=["Poop"])

    poop_color_options = ["black", "green", "yellow", "brown", "orange", "red", "white"]
    poop_color = st.sidebar.selectbox("Poop color:", poop_color_options, index=2)

    if st.sidebar.button("Diaper Change",icon="🩲", disabled=disable_push):
        log_event("Diaper Change")
        if "Pee" in poop_pee_selection:
            log_event("Pee")
        if "Poop" in poop_pee_selection:
            log_event(f"Poop, {poop_color}", comments=comments)

    
    st.sidebar.divider()
    if st.sidebar.button("Mom Painmeds",icon=":material/medication:", disabled=disable_push):
        log_event("Mom Painmeds")

    if st.sidebar.button("Prenatal vitamins", icon="💊", disabled=disable_push):
        log_event("Prenatal vitamins")

    if st.sidebar.button("Vitamin D", icon=":material/water_drop:", disabled=disable_push):
        log_event("Vitamin D")

    df = load_data(start_date)

    stats = st.toggle("Show daily stats")
    if stats:
        fig = create_radar_plot(df)
        st.plotly_chart(fig)

    # now_pdt = datetime.now(PDT).strftime("%Y-%m-%d %H:%M:%S %Z")
    # st.metric("**Current Time (PDT):**", now_pdt)

    st.subheader("Time since last")
    _,col3, col4,_  = st.columns(4)
    with col3:
        st.metric("🩲 Diaper change", time_since_last(df, "Diaper Change", start_date))
    with col4:
        st.metric("🍼 Feeding", time_since_last(df, "Breastfeeding", start_date))

    col4, col5,col6 = st.columns(3)
    with col4:
        st.metric(":woman: Pain Med", time_since_last(df, "Mom Painmeds", start_date))
    with col5:
        st.metric(":baby: Vitamin D", time_since_last(df, "Vitamin D", start_date))
    with col6:
        st.metric(":woman: Prenatal vitamins", time_since_last(df, "Prenatal vitamins", start_date))

    _,col1, col2,_ = st.columns(4)
    with col1:
        st.metric("Pee count", count_events(df, "Pee", start_date))
    with col2:
        st.metric("Poop count", count_events(df, "Poop", start_date))


    edit_mode = st.sidebar.checkbox("Edit Logs", disabled=disable_push)
    # edit_mode = False


    if edit_mode:
        df_edited = st.data_editor(df, column_config={
            'time': st.column_config.TimeColumn("Time")
        }, hide_index=True, disabled = ['rowid','date', 'timestamp' ])

        if st.button("Save Edits"):
            update_logs(df_edited)
            time.sleep(1)
            st.rerun()
    else:
        st.dataframe(df.drop(columns=['rowid','date','time']))


if __name__ == "__main__":
    main()