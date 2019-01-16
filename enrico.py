from dash.dependencies import Output, Input, State, Event
import dash_table
import dash_core_components as dcc
import dash_html_components as html
import msgpack
import os
import pandas as pd
import random
import sqlite3
import time

from nucypher.data_sources import DataSource
from umbral.keys import UmbralPublicKey

from app import app, DB_FILE, DB_NAME, SHARED_FOLDER

DATA_SOURCE_INFO_FILE = os.path.join(SHARED_FOLDER, 'heart_data.msgpack')

cached_data_source = list()

layout = html.Div([
    html.Div([
        html.Img(src='./assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.Div([
            html.Div([
                html.Img(src='./assets/enrico.png'),
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
        html.Div('Policy Key (hex): ', className='two columns'),
        dcc.Input(id='policy-pub-key', type='text', className='seven columns'),
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
     State('policy-pub-key', 'value'),
     State('cached-last-heartbeat', 'children')],
    [Event('gen-heartbeat-update', 'interval'),
     Event('generate-button', 'click')]
)
def generate_heartbeat_data(gen_time, policy_pubkey_hex, last_heart_rate):
    if int(gen_time) == 0:
        # button has not been clicked as yet or interval triggered before click
        # return base heart rate
        print('in here instead')
        return None

    print("in generate heartbeat data")

    label = 'heart-data'

    policy_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_pubkey_hex))
    if not cached_data_source:
        data_source = DataSource(policy_pubkey_enc=policy_pubkey, label=label)
        data_source_public_key = bytes(data_source.stamp)

        data = {
            'data_source_pub_key': data_source_public_key,
        }
        with open(DATA_SOURCE_INFO_FILE, "wb") as file:
            msgpack.dump(data, file, use_bin_type=True)
        cached_data_source.append(data_source)
    else:
        data_source = cached_data_source[0]

    if last_heart_rate is not None:
        last_heart_rate = int(last_heart_rate)
    else:
        last_heart_rate = 80

    heart_rate = random.randint(max(60, last_heart_rate - 5),
                                min(100, last_heart_rate + 5))

    plaintext = msgpack.dumps(heart_rate, use_bin_type=True)
    message_kit, _signature = data_source.encrypt_message(plaintext)
    kit_bytes = message_kit.to_bytes()

    timestamp = time.time()
    df = pd.DataFrame.from_dict({
        'Timestamp': [timestamp],
        'EncryptedData': [kit_bytes.hex()],
    })

    # add new heartbeat data
    db_conn = sqlite3.connect(DB_FILE)
    try:
        df.to_sql(name=DB_NAME, con=db_conn, index=False, if_exists='append')
        print("Added heart rate️ measurement to db:", timestamp, "-> ❤", heart_rate)
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
        df = pd.read_sql_query('SELECT Timestamp, EncryptedData '
                               'FROM {} '
                               'WHERE Timestamp > "{}" AND Timestamp <= "{}" '
                               'ORDER BY Timestamp DESC;'
                               .format(DB_NAME, now - duration, now), db_conn)
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
