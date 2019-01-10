import collections
from dash.dependencies import Output, Input, State, Event
import dash_core_components as dcc
import dash_html_components as html
import demo_keys
import json
import nucypher_helper
import pandas as pd
from plotly.graph_objs import Scatter, Layout, Figure
from plotly.graph_objs.layout import Margin
from plotly.graph_objs.scatter import *
import sqlite3
import time
from umbral import pre, config

from app import app, DB_FILE, TABLE_NAME

layout = html.Div([
    html.Div([
        html.Img(src='./assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.Div([
            html.Div([
                html.Img(src='./assets/bob.png'),
            ], className='two columns'),
            html.Div([
                html.Div([
                    html.H2('DR. BOB'),
                    html.P(
                        "Dr. Bob is Alicia's doctor and will be granted access by Alicia to access the encrypted "
                        "heart rate measurements database (which was populated by the Heart Monitor) and requests "
                        "a re-encrypted ciphertext for each measurement, which can then be decrypted "
                        "using the doctor's private key."),
                ], className="row")
            ], className='five columns'),
        ], className='row'),
    ], className='app_name'),
    html.Hr(),
    html.Button('Generate Key Pair',
                id='gen-key-button',
                type='submit',
                className='button button-primary'),
    html.Div([
        html.Div('Public Key:', className='two columns'),
        html.Div(id='pub-key', className='seven columns'),
    ], className='row'),
    html.Hr(),
    html.Div([
        html.H3('Heartbeats from Encrypted DB'),
        html.Div([
            html.Button('Read Heartbeats', id='read-button', type='submit',
                        className='button button-primary', n_clicks_timestamp='0'),
        ], className='row'),
        html.Div([
            dcc.Graph(id='heartbeats'),
        ]),
        dcc.Interval(id='heartbeat-update', interval=1000, n_intervals=0),
    ], className='row'),
    # Hidden div inside the app that stores previously decrypted heartbeats
    html.Div(id='latest-decrypted-heartbeats', style={'display': 'none'})
])


@app.callback(
    Output('latest-decrypted-heartbeats', 'children'),
    [],
    [State('read-button', 'n_clicks_timestamp'),
     State('latest-decrypted-heartbeats', 'children')],
    [Event('heartbeat-update', 'interval'),
     Event('read-button', 'click')]
)
def update_cached_decrypted_heartbeats_list(read_time, json_hb_values):
    if int(read_time) == 0:
        # button never clicked but triggered by interval
        return None

    cached_hb_values = collections.OrderedDict()
    if json_hb_values is not None:
        cached_hb_values = json.loads(json_hb_values, object_pairs_hook=collections.OrderedDict)

    last_timestamp = time.time() - 30  # last 30s
    if len(cached_hb_values) > 0:
        # use last timestamp
        last_timestamp = list(cached_hb_values.keys())[-1]

    db_conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('SELECT Timestamp, HB, Capsule '
                           'FROM {} '
                           'WHERE Timestamp > "{}" '
                           'ORDER BY Timestamp;'
                           .format(TABLE_NAME, last_timestamp), db_conn)

    for index, row in df.iterrows():
        timestamp = row['Timestamp']

        if row['Timestamp'] in cached_hb_values:
            # value already cached
            continue

        capsule = pre.Capsule.from_bytes(bytes.fromhex(row['Capsule']), params=config.default_params())
        hb_ciphertext = bytes.fromhex(row['HB'])

        alicia_pubkeys = demo_keys.get_alicia_pubkeys()
        bob_pubkeys = demo_keys.get_doctor_pubkeys()
        bob_privkeys = demo_keys.get_doctor_privkeys()
        nucypher_helper.reencrypt_data(alicia_pubkeys['enc'],
                                       bob_pubkeys['enc'],
                                       alicia_pubkeys['sig'],
                                       capsule)
        hb_bytes = pre.decrypt(ciphertext=hb_ciphertext,
                               capsule=capsule,
                               decrypting_key=bob_privkeys['enc'])
        hb = int.from_bytes(hb_bytes, byteorder='big')
        cached_hb_values[timestamp] = hb

    # only cache last 30s
    while len(cached_hb_values) > 30:
        cached_hb_values.popitem(False)

    return json.dumps(cached_hb_values)


@app.callback(
    Output('pub-key', 'children'),
    events=[Event('gen-key-button', 'click')]
)
def gen_doctor_pubkey():
    bob_pubkeys = demo_keys.get_doctor_pubkeys()
    return bob_pubkeys['enc'].to_bytes().hex()


@app.callback(
    Output('heartbeats', 'figure'),
    [Input('latest-decrypted-heartbeats', 'children')]
)
def update_graph(json_hb_values):
    if json_hb_values is None:
        return Figure(data=[])

    cached_hb_values = json.loads(json_hb_values, object_pairs_hook=collections.OrderedDict)
    if len(cached_hb_values) == 0:
        return Figure(data=[])

    df = pd.DataFrame({'HB': list(cached_hb_values.values())})

    trace = Scatter(
        y=df['HB'],
        line=Line(
            color='#1E65F3'
        ),
        mode='lines+markers',
    )

    layout = Layout(
        height=450,
        xaxis=dict(
            title='Time Elapsed (sec)',
            range=[0, 30],
            showgrid=False,
            showline=True,
            zeroline=False,
            fixedrange=True,
            tickvals=[0, 10, 20, 30],
            ticktext=['30', '20', '10', '0']
        ),
        yaxis=dict(
            title='Heart Rate (bpm)',
            range=[50, 110],
            showline=True,
            fixedrange=True,
            zeroline=False,
            nticks=10
        ),
        margin=Margin(
            t=45,
            l=50,
            r=50
        )
    )

    return Figure(data=[trace], layout=layout)
