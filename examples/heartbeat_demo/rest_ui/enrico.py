import json
import random
import sqlite3
import time

import dash_core_components as dcc
import dash_html_components as html
import dash_table
import pandas as pd
import requests
from examples.heartbeat_demo.rest_ui.app import app, DB_FILE, DB_NAME
from dash.dependencies import Output, Input, State, Event
from base64 import b64encode

ENRICO_URL = "http://localhost:5151"

layout = html.Div([
    html.Div([
        html.Img(src='/assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.Div([
            html.Div([
                html.Img(src='/assets/enrico.png'),
            ], className='two columns'),
            html.Div([
                html.Div([
                    html.H2('ENRICO'),
                    html.P("Enrico is the Heart Monitor that uses a data policy key to encrypt Alicia's "
                           "heart rate measurements readings into a database or some storage service "
                           "(e.g., IPFS, S3, whatever). Data Sources like the Heart Monitor remain "
                           "completely unaware of the recipients. In their mind, they are producing data "
                           "for Alicia. "),
                ], className="row")
            ], className='five columns'),
        ], className='row'),
    ], className='app_name'),
    html.Hr(),
    html.H3('Data Policy'),
    html.Div([
        html.Button('Start Monitoring', id='generate-button', type='submit',
                    className="button button-primary", n_clicks_timestamp='0'),
        dcc.Interval(id='gen-heartbeat-update', interval=1000, n_intervals=0),
    ], className='row'),
    html.Hr(),
    html.Div([
        html.H3('Encrypted Heartbeat Data in Database ❤'),
        html.Div([
            html.Div('Latest Heartbeat (❤ bpm): ', className='two columns'),
            html.Div(id='cached-last-heartbeat', className='one column'),
        ], className='row'),
        html.Br(),
        html.H5('Last 30s of Data: '),
        html.Div(id='db-table-content'),
    ], className='row'),
])


@app.callback(
    Output('cached-last-heartbeat', 'children'),
    [],
    [State('generate-button', 'n_clicks_timestamp'),
     State('cached-last-heartbeat', 'children')],
    [Event('gen-heartbeat-update', 'interval'),
     Event('generate-button', 'click')]
)
def generate_heartbeat_data(gen_time, last_heart_rate):
    if int(gen_time) == 0:
        # button has not been clicked as yet or interval triggered before click
        return None

    if last_heart_rate is not None:
        try:
            last_heart_rate = int(last_heart_rate)
        except ValueError:
            last_heart_rate = 80
    else:
        last_heart_rate = 80

    heart_rate = random.randint(max(60, last_heart_rate - 5),
                                min(100, last_heart_rate + 5))

    heart_rate_bytes = bytes(str(heart_rate), encoding='utf-8')

    # Use enrico character control to encrypt plaintext data using REST endpoint
    request_data = {
        'message': b64encode(heart_rate_bytes).decode()
    }

    response = requests.post(f'{ENRICO_URL}/encrypt_message', data=json.dumps(request_data))
    if response.status_code != 200:
        print(f'> WARNING: Problem encrypting plaintext message for heart rate {heart_rate} using enrico character '
              f'control - it will be ignored; status code = {response.status_code}; response = {response.content}')
        # just return previous successful added heart rate - ignore failed recent measurement
        return f'> WARNING: Problem encrypting plaintext message for heart rate {heart_rate} using enrico character ' \
               f'control - it will be ignored; status code = {response.status_code}'

    response_data = json.loads(response.content)
    message_kit = response_data['result']['message_kit']  # b64 str

    timestamp = time.time()
    df = pd.DataFrame.from_dict({
        'Timestamp': [timestamp],
        'EncryptedData': [message_kit],
    })

    # add new heartbeat data
    db_conn = sqlite3.connect(DB_FILE)
    try:
        df.to_sql(name=DB_NAME, con=db_conn, index=False, if_exists='append')
        print(f'Added heart rate️ measurement to db: {timestamp} -> ❤ {heart_rate}')
    finally:
        db_conn.close()

    return heart_rate


@app.callback(
    Output('db-table-content', 'children'),
    [Input('cached-last-heartbeat', 'children')]
)
def display_heartbeat_data(cached_last_heartbeat):
    if cached_last_heartbeat is None:
        # button hasn't been clicked as yet
        return ''

    now = time.time()
    duration = 30  # last 30s of readings
    db_conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query(f'SELECT Timestamp, EncryptedData '
                               f'FROM {DB_NAME} '
                               f'WHERE Timestamp > "{now - duration}" AND Timestamp <= "{now}" '
                               f'ORDER BY Timestamp DESC;',
                               db_conn)
        rows = df.to_dict('rows')
    finally:
        db_conn.close()

    return html.Div([
                dash_table.DataTable(
                    id='db-table',
                    columns=[{"name": i, "id": i} for i in df.columns],
                    data=rows,
                    style_table={
                        'maxHeight': '300',
                        'overflowY': 'scroll'
                    },
                    style_cell={
                        'textAlign': 'left',
                        'minWidth': '0px',
                        'maxWidth': '200px',
                        'whiteSpace': 'no-wrap',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                    },
                    css=[{
                        'selector': '.dash-cell div.dash-cell-value',
                        'rule': 'display: inline; white-space: inherit; overflow: inherit; text-overflow: inherit;'
                    }],
                )
           ], className='row')
