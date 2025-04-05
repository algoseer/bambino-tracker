# app.py
import streamlit as st
import sqlite3
import time
import pandas as pd
from functools import partial
from datetime import datetime, timedelta, date
import pytz
import plotly.graph_objects as go
import plotly.express as px

DATABASE_NAME = "baby_log.db"
PDT = pytz.timezone('US/Pacific')
yesterday = date.today() - timedelta(days=1)
start_date = st.sidebar.date_input("Show events from:", yesterday)
# Get the current time, and subtract 24 hours
now = datetime.now(PDT)
twenty_four_hours_ago = now - timedelta(hours=24)

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
    last_event_df = filtered_df[filtered_df['event'].str.startswith(event_type)]
    last_event = last_event_df['timestamp'].max()

    if pd.isnull(last_event):
        return "N/A"
    else:
        last_event_dt = PDT.localize(datetime.strptime(last_event, '%Y-%m-%d %H:%M:%S'))
        now_pdt = datetime.now(PDT)
        last_event_epoch = int(last_event_dt.timestamp())
        now_pdt_epoch = int(now_pdt.timestamp())
        time_diff_seconds = now_pdt_epoch - last_event_epoch
        time_diff = timedelta(seconds=time_diff_seconds)

        if event_type == "Breastfeeding":
            #For bf add modifier for side
            last_event_string = last_event_df[last_event_df['timestamp']==last_event]["event"].iloc[0]
            last_event_string = last_event_string.split(',')
            modifier = ''
            if 'R' in last_event_string:
                modifier += ":point_right:"
            if 'L' in last_event_string:
                modifier += ':point_left:'
            return time_diff, modifier
        else:
            return time_diff

def count_events(df, event_type, start_time):
    #only last 24 hrs not by date
    filtered_df = df[pd.to_datetime(df['timestamp']).dt.tz_localize(PDT) >= start_time]
    count = len(filtered_df[filtered_df['event'].str.startswith(event_type)])
    return count

def count_balance(df, start_date):
    filtered_df = df[pd.to_datetime(df['timestamp']).dt.date >= start_date]
    count = {"L":0, "R":0}
    for el in filtered_df['event']:
        if 'L' in el:
            count['L'] +=1
        if 'R' in el:
            count['R'] +=1

    fig = go.Figure(data=[go.Pie(labels=['left', 'right'], values=[count['L'], count['R']], marker_colors=['blue', 'red'])])
    fig.update_layout(
        title={
            'text': 'Feed stats',
            'y': 0.6,  # Adjust vertical position (0 to 1)
            'x': 0.6,  # Adjust horizontal position (0 to 1)
            'xanchor': 'center',  # Center the title horizontally
            'yanchor': 'top'  # Position the top of the title at the specified y-coordinate
        }
    )

    return count, fig

def analyze_sleep_durations(df,start_date):
    """
    Analyzes sleep durations from a DataFrame of events.

    Args:
        df (pd.DataFrame): DataFrame with 'timestamp' and 'event' columns.
        start_date (datetime.date): Date to start analysis from.

    Returns:
        list: A list of tuples, where each tuple contains (start_time, duration).
    """

    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(PDT)
    df = df[df['timestamp'].dt.date >= start_date].sort_values(by='timestamp')

    sleep_data = []
    sleep_start = None

    for index, row in df.iterrows():
        event = row['event']
        timestamp = row['timestamp']

        if event.startswith("Sleep"):
            sleep_start = timestamp
        elif sleep_start and (event.startswith('Diaper') or event.startswith('Breastfeeding')):
            sleep_end = timestamp
            duration = sleep_end - sleep_start
            sleep_data.append((sleep_start, duration))
            sleep_start = None  # Reset sleep start

    if sleep_data:
        sleep_df = pd.DataFrame(sleep_data, columns=['start_time', 'duration'])
        return sleep_df
    else:
        return pd.DataFrame(columns=['start_time', 'duration']) # return empty dataframe if no results.

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
    # Filter the DataFrame
    df_filtered = df_filtered[ts >= twenty_four_hours_ago]

    categories = ['Sleep','Breastfeeding', 'Pee', 'Poop']
    colors = ['magenta','brown', 'blue', 'green']
    markers = ['asterisk-open','circle-open-dot','square-open', 'x']
    fig = go.Figure()

    idx = 0.5
    date = df_filtered['date'].iloc[-1]
    for marker, category, color in zip(markers, categories, colors):
        filtered_events = df_filtered[df_filtered['event'].str.startswith(category)]
        times = [(t.hour + t.minute / 60)*360/24 for t in filtered_events['time']]
        dates = [1 if d==date else 0 for d in filtered_events['date']]
        comments = [a if a else "" for a in filtered_events['comments']]
        fig.add_trace(go.Scatterpolar(
            r=[idx-0.2*d for d in dates],
            theta=times,
            mode='markers',
            customdata=comments,
            marker=dict(symbol=marker,color=color, size=8),
            name=category,
            hovertemplate="%{customdata}<extra></extra>",
        ))
        idx+=0.4

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


    disable_push =  bool(int(st.query_params.get("viewonly", "0")))


    comments = st.sidebar.text_input("Comments")

    feeding_options = [":point_left:", ":point_right:"]
    feeding_selection = st.sidebar.segmented_control("", feeding_options, selection_mode="multi", default=[])
    if st.sidebar.button("Breastfeeding",icon="🍼", disabled=disable_push):
        event = ["Breastfeeding"]
        if ':point_left:' in feeding_selection:
            event += 'L'
        if ':point_right:' in feeding_selection:
            event += 'R'

        event= ','.join(event)
        log_event(event, comments=comments)

    if st.sidebar.button("Sleep", icon="😴", disabled = disable_push):
        log_event('Sleep', comments=comments)

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
        cola, colb= st.columns(2)
        with cola:
            fig = create_radar_plot(df)
            st.plotly_chart(fig)
        with colb:
            ctr, fig = count_balance(df, start_date)
            st.plotly_chart(fig)

        colc, cold = st.columns(2)

        def dt_to_hr_mins(time):
            total_seconds = time.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return hours, minutes
        
        def format_timestamp_with_day_period(timestamp):
            """Formats a timestamp to 'YYYY-MM-DD / Afternoon / 3:43 PM' or 'YYYY-MM-DD / Morning' etc."""
            if not isinstance(timestamp, datetime):
                raise TypeError("Input must be a datetime object")

            hour = timestamp.hour
            date_str = timestamp.strftime("%Y-%m-%d")
            time_str = timestamp.strftime("%I:%M %p") # 12-hour format with AM/PM

            if 6 <= hour < 12:
                return f"{date_str} / Morning / {time_str}"
            elif 12 <= hour < 17:
                return f"{date_str} / Afternoon / {time_str}"
            elif 17 <= hour < 22:
                return f"{date_str} / Evening / {time_str}"
            else:
                return f"{date_str} / Night / {time_str}"

        with colc:
            sleep_df = analyze_sleep_durations(df, start_date)
            last_duration = sleep_df['duration'].iloc[-1]
            avg_duration = sleep_df['duration'].median()
            max_duration = sleep_df['duration'].max()

            hours, minutes = dt_to_hr_mins(last_duration)
            st.metric(f"Last sleep duration", f"{hours:02d}:{minutes:02d}")

            hours, minutes = dt_to_hr_mins(avg_duration)
            st.metric(f"Average sleep duration (24h)", f"{hours:02d}:{minutes:02d}")

            hours, minutes = dt_to_hr_mins(max_duration)
            st.metric(f"Longest sleep duration (24h)", f"{hours:02d}:{minutes:02d}")


        with cold:
            sleep_df = sleep_df.sort_values(by='duration', ascending=False).reset_index(drop=True)
            sleep_df["start_time"] = sleep_df['start_time'].apply(format_timestamp_with_day_period)
            st.markdown(":green[Top scores last 24 hrs]")
            st.dataframe(sleep_df.head(5), hide_index=True)

        st.divider()

    # now_pdt = datetime.now(PDT).strftime("%Y-%m-%d %H:%M:%S %Z")
    # st.metric("**Current Time (PDT):**", now_pdt)

    st.subheader("Time since last")
    col3, col4, col4b  = st.columns(3)
    with col3:
        last_time_diaper = time_since_last(df, "Diaper Change", start_date)
        st.metric("🩲 Diaper change", str(last_time_diaper))
    with col4:
        #Find last feeding side
        last_time_feeding, modifier = time_since_last(df, "Breastfeeding", start_date)
        st.metric(f"🍼 Feeding {modifier}", str(last_time_feeding))
    with col4b:
        #Find last feeding side
        last_time = time_since_last(df, "Sleep", start_date)
        if last_time < last_time_diaper and last_time < last_time_feeding:
            st.metric(f":sleeping: Sleep", str(last_time))
        else:
            st.metric(f":sleeping: Sleep", "N/A")

    col4, col5,col6 = st.columns(3)
    with col4:
        st.metric(":woman: Pain Med", str(time_since_last(df, "Mom Painmeds", start_date)))
    with col5:
        st.metric(":baby: Vitamin D", str(time_since_last(df, "Vitamin D", start_date)))
    with col6:
        st.metric(":woman: Prenatal vitamins", str(time_since_last(df, "Prenatal vitamins", start_date)))


    _,col1, col2, _ = st.columns(4)
    with col1:
        st.metric("Pee count", count_events(df, "Pee", twenty_four_hours_ago))
    with col2:
        st.metric("Poop count", count_events(df, "Poop", twenty_four_hours_ago))



    edit_mode = st.sidebar.checkbox("Edit Logs", disabled=disable_push)
    # edit_mode = False


    if edit_mode:
        df_edited = st.data_editor(df, column_config={
            'time': st.column_config.TimeColumn("Time")
        }, hide_index=True, disabled = ['rowid', 'timestamp' ])

        if st.button("Save Edits"):
            update_logs(df_edited)
            time.sleep(1)
            st.rerun()
    else:
        st.dataframe(df.drop(columns=['rowid','date','time']))


if __name__ == "__main__":
    main()