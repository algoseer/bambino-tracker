import paho.mqtt.client as mqtt
import json
import sqlite3
from datetime import datetime, timedelta, date
from functools import partial
import pytz
import pandas as pd
from config import *

# MQTT topic to subscribe to
MQTT_TOPIC = f"{ADAFRUIT_IO_USERNAME}/feeds/{ADAFRUIT_IO_FEED}"
MQTT_BROKER_URL = "io.adafruit.com"
MQTT_BROKER_PORT = 1883

## DB details
DATABASE_NAME = "baby_log.db"
PDT = pytz.timezone('US/Pacific')

## define all functions for database manipulation
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
    print(f"Logged: {event} at {now_utc.astimezone(PDT).strftime('%Y-%m-%d %H:%M:%S')} PDT")

def update_logs(df_edited):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        for index, row in df_edited.iterrows():
            # st.markdown(edited_df)
            combined_datetime = PDT.localize(datetime.combine(row['date'], row['time']))
            combined_datetime_utc = combined_datetime.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
            if row['comments']:
                combined_event_comment = f"{row['event']}+{row['comments']}"
            else:
                combined_event_comment =  row["event"]

            c.execute("UPDATE baby_events SET timestamp = ?, event = ? WHERE rowid = ?", (combined_datetime_utc, combined_event_comment, row['rowid']))
        conn.commit()
        conn.close()
    except ValueError:
        st.error("Invalid timestamp format.")

def load_data(start_date):
    def extract_comment(s, idx=1):
        if isinstance(s, str) and '+' in s:
            try:
                return s.split('+')[idx]
            except IndexError:
                return "" # Handles cases where there's no element at index 1
        else:
            return s if idx==0 else None   # Handles non-string or no '+' cases

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

        return time_diff


def add_time_to_last_event(df, time_to_add, start_date, event_type="Breastfeeding"):
    filtered_df = df[pd.to_datetime(df['timestamp']).dt.date >= start_date] #this is in pdt
    last_event_df = filtered_df[filtered_df['event'].str.startswith(event_type)]
    last_event = last_event_df['timestamp'].max()

    if pd.isnull(last_event):
        return "N/A"
    else:
        comment = f"Lasted {time_to_add}"
        edited_df = last_event_df[last_event_df['timestamp']==last_event]
        edited_df["comments"] = comment

        update_logs(edited_df)


# Callback function for when the client connects to the MQTT broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to Adafruit IO MQTT broker at {MQTT_BROKER_URL}:{MQTT_BROKER_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"Subscribed to feed: {MQTT_TOPIC}")
    else:
        print(f"Failed to connect to MQTT broker with result code {rc}")

# Callback function for when a message is received on the subscribed topic
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        if payload == "Feeding":
            log_event("Breastfeeding")
        elif payload=="Diaper":
            log_event("Diaper Change")
            log_event("Pee")
        elif payload=="Stop Feeding":
            start_date = date.today() - timedelta(days=1)
            df = load_data(start_date)
            time_to_update = time_since_last(df, "Breastfeeding", start_date)
            print(start_date, time_to_update)
            add_time_to_last_event(df, time_to_update, start_date)

            now_utc = datetime.utcnow()
            now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Logged: {payload} at {now_utc.astimezone(PDT).strftime('%Y-%m-%d %H:%M:%S')} PDT")

    except Exception as e:
        print(f"Error processing message: {e}")


if __name__ == '__main__':
    # Create an MQTT client instance
    client = mqtt.Client()

    # Set the username and password for Adafruit IO
    client.username_pw_set(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

    # Set the callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to the Adafruit IO MQTT broker
    try:
        client.connect(MQTT_BROKER_URL, MQTT_BROKER_PORT, 60)
    except Exception as e:
        print(f"Error connecting to MQTT broker: {e}")
        exit()

    # Start the MQTT client loop to listen for incoming messages
    client.loop_forever()