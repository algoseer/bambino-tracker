import pandas as pd
import pytz, sqlite3
from functools import partial
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
from fpdf import FPDF
from io import BytesIO
import base64

# Assuming you have these functions defined elsewhere:
# load_data, time_since_last, count_events, create_radar_plot, analyze_sleep_durations_df
DATABASE_NAME = "baby_log.db"
PDT = pytz.timezone('US/Pacific')

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
            return str(time_diff), modifier
        else:
            return str(time_diff)

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


def calculate_average_sleep_duration(sleep_df):
    avg_duration = sleep_df['duration'].mean()
    total_seconds = avg_duration.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return hours, minutes

#Plot data that is showing in the table below on a radar plot
def create_radar_plot(df,  twenty_four_hours_ago, timestamp_column='timestamp'):

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


### END OF function copy

def generate_pdf_report_fpdf(df, start_date, twenty_four_hours_ago):
    """Generates a PDF report using FPDF."""

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Baby Tracking System Report", 0, 1, 'C')

    pdf.set_font("Arial","", 12)
    pdf.ln(10)


    sleep_time=time_since_last(df, 'Sleep', start_date)
    feeding_time=time_since_last(df, 'Breastfeeding', start_date)[0]
    diaper_time=time_since_last(df, 'Diaper Change', start_date)

    if sleep_time>feeding_time or sleep_time>diaper_time:
        sleep_time="N/A"

    # Table Data
    table_data = [
        ["Current Time (PDT)", datetime.now(PDT).strftime('%Y-%m-%d %H:%M:%S %Z')],
        ["Time since last diaper change", time_since_last(df, 'Diaper Change', start_date)],
        ["Time since last feeding", time_since_last(df, 'Breastfeeding', start_date)[0]],
        ["Time since sleep", sleep_time],
        ["Time since last pain med", time_since_last(df, 'Mom Painmeds', start_date)],
        ["Time since last Vitamin D", time_since_last(df, 'Vitamin D', start_date)],
        ["Time since last Prenatal vitamins", time_since_last(df, 'Prenatal vitamins', start_date)],
        ["Pee count", count_events(df, 'Pee',  twenty_four_hours_ago)],
        ["Poop count", count_events(df, 'Poop', twenty_four_hours_ago)],
    ]

    # Create Table
    col_width = pdf.w / 2.1 # adjust as needed.
    row_height = 10

    for row in table_data:
        for item in row:
            pdf.cell(col_width, row_height, str(item), 1)
        pdf.ln(row_height)

    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Sleep Data", 0, 1)
    pdf.set_font("Arial", "", 12)
    sleep_df = analyze_sleep_durations(df, start_date)

    avg_duration = sleep_df['duration'].median()
    max_duration = sleep_df['duration'].max()

    sleep_df = sleep_df.sort_values(by='duration', ascending=False).reset_index(drop=True)
    sleep_df["start_time"] = sleep_df['start_time'].apply(format_timestamp_with_day_period)
    sleep_df = sleep_df.head(5)

    if not sleep_df.empty:
        h, m = dt_to_hr_mins(avg_duration)
        pdf.cell(0, 10, f"Average sleep duration: {h:02d}:{m:02d}", 0, 1)
        h, m = dt_to_hr_mins(max_duration)
        pdf.cell(0, 10, f"Max sleep duration: {h:02d}:{m:02d}", 0, 1)
        for index, row in sleep_df.iterrows():
            pdf.cell(0, 10, f"Start: {row['start_time']},  Duration: {row['duration']}", 0, 1)
    else:
        pdf.cell(0,10, "No Sleep data available",0,1)

    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Activity Radar Plot", 0, 1)

    fig = create_radar_plot(df, twenty_four_hours_ago)
    img_data = fig.to_image(format="png")
    img_base64 = base64.b64encode(img_data).decode("utf-8")
    img_io = BytesIO(base64.b64decode(img_base64))

    pdf.image(img_io, w=150)

    return pdf.output(dest='S')

def do_report():

    yesterday = date.today() - timedelta(days=1)
    start_date = yesterday

    # Get the current time, and subtract 24 hours
    now = datetime.now(PDT)
    twenty_four_hours_ago = now - timedelta(hours=24)

    df = load_data(start_date)
    report_pdf_fpdf = generate_pdf_report_fpdf(df, start_date, twenty_four_hours_ago)
    with open("report.pdf", "wb") as f:
        f.write(report_pdf_fpdf)

if __name__ == '__main__':
    do_report()