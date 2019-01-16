import collections
from dash.dependencies import Output, Input, State, Event
import dash_core_components as dcc
import dash_html_components as html
import demo_keys
import json
import os
import pandas as pd
from plotly.graph_objs import Scatter, Layout, Figure
from plotly.graph_objs.layout import Margin
from plotly.graph_objs.scatter import *
import sqlite3
import time

from app import app, DB_FILE, DB_NAME

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
            html.H3('Heartbeats from Encrypted DB'),
            html.Div([
                html.Button('Read Heartbeats', id='read-button', type='submit',
                            className='button button-primary', n_clicks_timestamp='0'),
            ], className='row'),
            html.Div(id='heartbeats', className='row'),
            dcc.Interval(id='heartbeat-update', interval=1000, n_intervals=0),
        ], className='row'),
        # Hidden div inside the app that stores previously decrypted heartbeats
        html.Div(id='latest-decrypted-heartbeats', style={'display': 'none'})
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
    Output('latest-decrypted-heartbeats', 'children'),
    [],
    [State('read-button', 'n_clicks_timestamp'),
     State('latest-decrypted-heartbeats', 'children'),
     State('bob-unique-id', 'children')],
    [Event('heartbeat-update', 'interval'),
     Event('read-button', 'click')]
)
def update_cached_decrypted_heartbeats_list(read_time, json_latest_values, bob_id):
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
        print("The Doctor joins policy for label '{}' "
              "and pubkey {}".format(policy_data['label'], policy_data['policy_pubkey']))

        bob.join_policy(label, alices_sig_pubkey)
        joined.append(label)

    with open(DATA_SOURCE_INFO_FILE, "rb") as file:
        data_source_metadata = msgpack.load(file, raw=False)

    cached_hb_values = collections.OrderedDict()
    if (json_latest_values is not None) and (json_latest_values != ACCESS_REVOKED):
        cached_hb_values = json.loads(json_latest_values, object_pairs_hook=collections.OrderedDict)

    last_timestamp = time.time() - 5  # last 5s
    if len(cached_hb_values) > 0:
        # use last timestamp
        last_timestamp = list(cached_hb_values.keys())[-1]

    # Bob also needs to create a view of the Data Source from its public keys
    data_source = DataSource.from_public_keys(
        policy_public_key=policy_pubkey,
        datasource_public_key=data_source_metadata['data_source_pub_key'],
        label=label
    )

    db_conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query('SELECT Timestamp, EncryptedData '
                               'FROM {} '
                               'WHERE Timestamp > "{}" '
                               'ORDER BY Timestamp;'.format(DB_NAME, last_timestamp),
                               db_conn)

        for index, row in df.iterrows():
            kit_bytes = bytes.fromhex(row['EncryptedData'])
            message_kit = UmbralMessageKit.from_bytes(kit_bytes)

            # Now he can ask the NuCypher network to get a re-encrypted version of each MessageKit.
            try:
                retrieved_plaintexts = bob.retrieve(
                    message_kit=message_kit,
                    data_source=data_source,
                    alice_verifying_key=alices_sig_pubkey
                )

                hb = msgpack.loads(retrieved_plaintexts[0], raw=False)
            except Exception as e:
                print(str(e))
                continue

            timestamp = row['Timestamp']
            cached_hb_values[timestamp] = hb
    finally:
        db_conn.close()

    # only cache last 30s
    while len(cached_hb_values) > 30:
        cached_hb_values.popitem(False)

    return json.dumps(cached_hb_values)


@app.callback(
    Output('heartbeats', 'children'),
    [Input('latest-decrypted-heartbeats', 'children')]
)
def update_graph(json_cached_readings):
    if json_cached_readings is None:
        return ''

    if json_cached_readings == ACCESS_REVOKED:
        return html.Div('Your access has either not been granted or has been revoked!', style={'color': 'red'})

    cached_hb_values = json.loads(json_cached_readings, object_pairs_hook=collections.OrderedDict)
    if len(cached_hb_values) == 0:
        return ''

    df = pd.DataFrame({'HB': list(cached_hb_values.values())})

    trace = Scatter(
        y=df['HB'],
        line=Line(
            color='#1E65F3'
        ),
        mode='lines+markers',
    )

    graph_layout = Layout(
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

    return dcc.Graph(id='hb_table', figure={'data': [trace], 'layout': graph_layout})
