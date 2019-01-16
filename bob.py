from dash.dependencies import Output, Input, State, Event
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import demo_keys
import json
import os
import pandas as pd
from plotly.graph_objs import Scatter
from plotly.graph_objs.layout import Margin
from plotly.graph_objs.scatter import *
import sqlite3
import time

from app import app, DB_FILE, DB_NAME, PROPERTIES

import shutil
import msgpack

from nucypher.characters.lawful import Bob, Ursula
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.data_sources import DataSource
from nucypher.keystore.keypairs import DecryptingKeypair, SigningKeypair
from nucypher.network.middleware import RestMiddleware

from umbral.keys import UmbralPublicKey

from enrico import DATA_SOURCE_INFO_FILE
from alicia import POLICY_INFO_FILE

ACCESS_REVOKED = "Access Disallowed"


######################
# Boring setup stuff #
######################

SEEDNODE_URL = "127.0.0.1:10151"

# TODO: path joins?
TEMP_DOCTOR_DIR = "{}/bob-files".format(os.path.dirname(os.path.abspath(__file__)))

TEMP_URSULA_CERTIFICATE_DIR = "{}/ursula-certs".format(TEMP_DOCTOR_DIR)
TEMP_DOCTOR_CERTIFICATE_DIR = "{}/bob-certs".format(TEMP_DOCTOR_DIR)

# Remove previous demo files and create new ones
shutil.rmtree(TEMP_DOCTOR_DIR, ignore_errors=True)
os.mkdir(TEMP_DOCTOR_DIR)
os.mkdir(TEMP_URSULA_CERTIFICATE_DIR)
os.mkdir(TEMP_DOCTOR_CERTIFICATE_DIR)

ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URL,
                                         federated_only=True,
                                         minimum_stake=0)

bob_privkeys = demo_keys.get_recipient_privkeys("bob")

bob_enc_keypair = DecryptingKeypair(private_key=bob_privkeys["enc"])
bob_sig_keypair = SigningKeypair(private_key=bob_privkeys["sig"])
enc_power = DecryptingPower(keypair=bob_enc_keypair)
sig_power = SigningPower(keypair=bob_sig_keypair)
power_ups = [enc_power, sig_power]

print("Creating Bob ...")

bob = Bob(
    is_me=True,
    federated_only=True,
    crypto_power_ups=power_ups,
    start_learning_now=True,
    abort_on_learning_error=True,
    known_nodes=[ursula],
    save_metadata=False,
    network_middleware=RestMiddleware(),
)

print("Bob = ", bob)

joined = list()


def get_layout():
    unique_id = 'bob'

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
                        html.H2('INSURER BOB'),
                        html.P(
                            "Bob is Alicia's Insurer and will be granted access by Alicia "
                            "to access the encrypted vehicle data database and requests a re-encrypted ciphertext for "
                            "each set of timed measurements, which can then be decrypted using the Insurer's "
                            "private key."),
                    ], className="row")
                ], className='five columns'),
            ], className='row'),
        ], className='app_name'),
        html.Hr(),
        html.Div([
            html.H3('Properties'),
            html.Div([
                html.Div('Unique Bob Id:', className='two columns'),
                html.Div(id='bob-unique-id', children='{}'.format(unique_id), className='one column'),
            ], className='row'),
            html.Br(),
            html.Button('Generate Key Pair',
                        id='gen-key-button',
                        type='submit',
                        className='button button-primary'),
            html.Div([
                html.Div('Public Key:', className='two columns'),
                html.Div(id='pub-key', className='seven columns'),
            ], className='row'),
        ]),
        html.Hr(),
        html.Div([
            html.H3('Vehicle Data from Encrypted DB'),
            html.Div([
                html.Button('Read Measurements', id='read-button', type='submit',
                            className='button button-primary', n_clicks_timestamp='0'),
            ], className='row'),
            html.Div(id='measurements', className='row'),
            dcc.Interval(id='measurements-update', interval=1000, n_intervals=0),
        ], className='row'),
        # Hidden div inside the app that stores previously decrypted measurements
        html.Div(id='latest-decrypted-measurements', style={'display': 'none'}),
    ])

    return layout


@app.callback(
    Output('pub-key', 'children'),
    [],
    [State('bob-unique-id', 'children')],
    [Event('gen-key-button', 'click')]
)
def gen_doctor_pubkey(bob_id):
    bob_pubkeys = demo_keys.get_recipient_pubkeys(bob_id)
    return bob_pubkeys['enc'].to_bytes().hex()


@app.callback(
    Output('latest-decrypted-measurements', 'children'),
    [],
    [State('read-button', 'n_clicks_timestamp'),
     State('latest-decrypted-measurements', 'children'),
     State('bob-unique-id', 'children')],
    [Event('measurements-update', 'interval'),
     Event('read-button', 'click')]
)
def update_cached_decrypted_measurements_list(read_time, df_json_latest_measurements, bob_id):
    if int(read_time) == 0:
        # button never clicked but triggered by interval
        return None

    # Let's join the policy generated by Alicia. We just need some info about it.
    with open(POLICY_INFO_FILE, 'r') as f:
        policy_data = json.load(f)

    policy_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data['policy_pubkey']))
    alices_sig_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data['alice_sig_pubkey']))
    label = policy_data['label'].encode()

    if not joined:
        print("The Insurer joins policy for label '{}' "
              "and pubkey {}".format(policy_data['label'], policy_data['policy_pubkey']))

        bob.join_policy(label, alices_sig_pubkey)
        joined.append(label)

    with open(DATA_SOURCE_INFO_FILE, "rb") as file:
        data_source_metadata = msgpack.load(file, raw=False)

    df = pd.DataFrame()
    last_timestamp = time.time() - 5  # last 5s
    if (df_json_latest_measurements is not None) and (df_json_latest_measurements != ACCESS_REVOKED):
        df = pd.read_json(df_json_latest_measurements, convert_dates=False)
        if len(df) > 0:
            # sort readings and order by timestamp
            df = df.sort_values(by='timestamp')
            # use last timestamp
            last_timestamp = df['timestamp'].iloc[-1]

    # Bob also needs to create a view of the Data Source from its public keys
    data_source = DataSource.from_public_keys(
        policy_public_key=policy_pubkey,
        datasource_public_key=data_source_metadata['data_source_pub_key'],
        label=label
    )

    db_conn = sqlite3.connect(DB_FILE)
    try:
        encrypted_df_readings = pd.read_sql_query('SELECT Timestamp, EncryptedData '
                                                  'FROM {} '
                                                  'WHERE Timestamp > "{}" '
                                                  'ORDER BY Timestamp '
                                                  'LIMIT 30;'.format(DB_NAME, last_timestamp),
                                                  db_conn)

        for index, row in encrypted_df_readings.iterrows():
            kit_bytes = bytes.fromhex(row['EncryptedData'])
            message_kit = UmbralMessageKit.from_bytes(kit_bytes)

            # Now he can ask the NuCypher network to get a re-encrypted version of each MessageKit.
            try:
                retrieved_plaintexts = bob.retrieve(
                    message_kit=message_kit,
                    data_source=data_source,
                    alice_verifying_key=alices_sig_pubkey
                )

                plaintext = msgpack.loads(retrieved_plaintexts[0], raw=False)
            except Exception as e:
                print(str(e))
                continue

            readings = plaintext['carInfo']
            readings['timestamp'] = row['Timestamp']
            df = df.append(readings, ignore_index=True)
    finally:
        db_conn.close()

    # only cache last 30 readings
    rows_to_remove = len(df) - 30
    if rows_to_remove > 0:
        df = df.iloc[rows_to_remove:]

    return df.to_json()


@app.callback(
    Output('measurements', 'children'),
    [Input('latest-decrypted-measurements', 'children')]
)
def update_graph(df_json_latest_measurements):
    divs = list()

    if df_json_latest_measurements is None:
        return divs

    if df_json_latest_measurements == ACCESS_REVOKED:
        return html.Div('Your access has either not been granted or has been revoked!', style={'color': 'red'})

    df = pd.read_json(df_json_latest_measurements, convert_dates=False)
    if len(df) == 0:
        return divs

    # sort readings and order by timestamp
    df = df.sort_values(by='timestamp')

    # add data table
    divs.append(html.Div([
        html.H5("Last 30s of Data"),
        html.Div(get_latest_datatable(df), className='row')])
    )

    # add graphs/figures
    inner_divs = list()
    num_divs_per_row = 2
    inner_div_class = 'six columns'  # 12/2 = 6
    for key in PROPERTIES.keys():
        if key in ['engineOn', 'gpsTime', 'vss', 'lat']:
            # properties not to be graphed

            # vss already plotted with rpm
            # lat already plotted with lon
            continue
        elif key == 'rpm':
            generated_div = html.Div(get_rpm_speed_graph(df), className=inner_div_class)
        elif key == 'lon':
            generated_div = html.Div(get_lon_lat_graph(df), className=inner_div_class)
        else:
            generated_div = html.Div(get_generic_graph_over_time(df, key), className=inner_div_class)

        inner_divs.append(generated_div)
        if len(inner_divs) == num_divs_per_row:
            divs.append(html.Div(children=inner_divs, className='row'))
            inner_divs = list()

    if len(inner_divs) > 0:
        # extra div remaining
        divs.append(html.Div(children=inner_divs, className='row'))

    return divs


def get_latest_datatable(df: pd.DataFrame) -> dash_table.DataTable:
    rows = df.sort_values(by='timestamp', ascending=False).to_dict('rows')
    return dash_table.DataTable(
        id='latest-data-table',
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


def get_generic_graph_over_time(df: pd.DataFrame, key: str) -> dcc.Graph:
    data = Scatter(
        y=df[key],
        fill='tozeroy',
        line=dict(
            color='#1E65F3',
        ),
        fillcolor='#9DC3E6',
        mode='lines+markers',
    )

    graph_layout = dict(
        title='{}'.format(PROPERTIES[key]),
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
            title='{}'.format(PROPERTIES[key]),
            range=[min(df[key]), max(df[key])],
            zeroline=False,
            fixedrange=False),
        margin=Margin(
            t=45,
            l=50,
            r=50
        )
    )

    return dcc.Graph(id=key, figure={'data': [data], 'layout': graph_layout})


def get_rpm_speed_graph(df: pd.DataFrame) -> dcc.Graph:
    rpm_data = Scatter(
        y=df['rpm'],
        name='RPM',
        mode='lines+markers'
    )
    speed_data = Scatter(
        y=df['vss'],
        name='Speed',
        mode='lines+markers',
        yaxis='y2'
    )

    graph_layout = dict(
        title='RPM and Speed',
        xaxis=dict(
            title='Time Elapsed (sec)',
            range=[0, 30],
            fixedrange=True,
            tickvals=[0, 10, 20, 30],
            ticktext=['30', '20', '10', '0']
        ),
        yaxis=dict(
            title='{}'.format(PROPERTIES['rpm']),
            zeroline=False,
        ),
        yaxis2=dict(
            title='{}'.format(PROPERTIES['vss']),
            overlaying='y',
            side='right',
            zeroline=False,
        ),
        legend={'x': 0, 'y': 1},
        margin=Margin(
            t=45,
            l=50,
            r=50
        )
    )

    return dcc.Graph(id='rpm_speed', figure={'data': [rpm_data, speed_data], 'layout': graph_layout})


def get_lon_lat_graph(df: pd.DataFrame) -> dcc.Graph:
    data = dict(
        type='scattergeo',
        locationmode='USA-states',
        lon=df['lon'],
        lat=df['lat'],
        mode='markers',
        marker=dict(
            size=8,
            opacity=0.8,
            reversescale=True,
            autocolorscale=False,
            symbol='square',
            line=dict(
                width=1,
                color='rgb(102, 102, 102)'
            ),
        ))

    graph_layout = dict(
        title='Longitude and Latitude',
        colorbar=True,
        geo=dict(
            scope='usa',
            projection=dict(type='albers usa'),
            showland=True,
            landcolor="rgb(250, 250, 250)",
            subunitcolor="rgb(217, 217, 217)",
            countrycolor="rgb(217, 217, 217)",
        ),
    )

    return dcc.Graph(id='lon_lat', figure={'data': [data], 'layout': graph_layout})
