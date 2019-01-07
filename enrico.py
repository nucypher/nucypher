from dash.dependencies import Output, Input, State, Event
from dash_table_experiments import DataTable
import dash_core_components as dcc
import dash_html_components as html
import pandas as pd
import random
import sqlite3
import time
from umbral import pre
from umbral.keys import UmbralPublicKey

from app import app, DB_FILE

layout = html.Div([
    html.Div([
        html.Img(src='./assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.H2('ENRICO'),
        html.P("<blurb about Enrico>")
    ], className='app_name'),
    html.Hr(),
    html.H3('Data Policy'),
    html.Div([
        html.Div('Policy Key (hex): ', className='two columns'),
        dcc.Input(id='policy-pub-key', type='text', className='seven columns'),
        html.Button('Generate Encrypted Heartbeats', id='generate-button', type='submit',
                    className="button button-primary", n_clicks_timestamp='0'),
        html.Div(id='cached-last-heartbeat', style={'display': 'none'}),
        dcc.Interval(id='gen-heartbeat-update', interval=1000, n_intervals=0),
    ], className='row'),
    html.Hr(),
    html.Div([
        html.H3('Encrypted Heartbeat Data in Database ❤'),
        html.Div(id='db-table-content'),
    ], className='row'),
])


@app.callback(
    Output('cached-last-heartbeat', 'children'),
    [],
    [State('generate-button', 'n_clicks_timestamp'),
     State('policy-pub-key', 'value'),
     State('cached-last-heartbeat', 'children')],
    [Event('gen-heartbeat-update', 'interval'),
     Event('generate-button', 'click')]
)
def generate_heartbeat_data(gen_time, policy_pubkey_hex, last_heart_rate):
    if int(gen_time) == 0:
        # button has not been clicked as yet or interval triggered before click
        # return base heart rate
        return None

    last_heart_rate = 80
    if last_heart_rate is not None:
        last_heart_rate = int(last_heart_rate)

    heart_rate = random.randint(max(60, last_heart_rate - 5),
                                min(100, last_heart_rate + 5))

    policy_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_pubkey_hex))
    ciphertext, capsule = pre.encrypt(policy_pubkey, int.to_bytes(heart_rate, length=1, byteorder='big'))

    timestamp = time.time()
    df = pd.DataFrame.from_dict({
        'Timestamp': [timestamp],
        'HR': [ciphertext.hex()],
        'Capsule': [capsule.to_bytes().hex()]
    })

    # generate new heartbeat data
    db_conn = sqlite3.connect(DB_FILE)
    df.to_sql(name='HeartRates', con=db_conn, index=False, if_exists='append')
    print("Added heart rate️ measurement to db:", timestamp, "-> ❤", heart_rate)

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
    df = pd.read_sql_query('SELECT Timestamp, HR, Capsule '
                           'FROM HeartRates '
                           'WHERE Timestamp > "{}" AND Timestamp <= "{}" '
                           'ORDER BY Timestamp DESC;'
                           .format(now - duration, now), db_conn)
    rows = df.to_dict('rows')

    return html.Div([
        html.Div(id='datatable-output'),
        DataTable(
            id='datatable',
            rows=rows,
        )
    ])
