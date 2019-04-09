import collections
import json
import os
import random
import shutil
import sqlite3
import time
import traceback

import dash_core_components as dcc
import dash_html_components as html
import msgpack
import pandas as pd
from dash.dependencies import Output, Input, State, Event
from plotly.graph_objs import Scatter, Layout
from plotly.graph_objs.layout import Margin
from plotly.graph_objs.scatter import *
from umbral.keys import UmbralPublicKey

from examples.utilities.demo_keys import DemoKeyGenerator, ENCRYPTING_KEY, VERIFYING_KEY
from examples.heartbeat_demo_ui.app \
    import app, DB_FILE, DB_NAME, SEEDNODE_URL, POLICY_INFO_FILE, DATA_SOURCE_INFO_FILE, BOB_FOLDER, KEYS_FOLDER
from nucypher.characters.lawful import Bob, Ursula, Enrico
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.keystore.keypairs import DecryptingKeypair, SigningKeypair
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.middleware import MockRestMiddleware

ACCESS_DISALLOWED = "Access Disallowed"


######################
# Boring setup stuff #
######################

bob_instances = dict()  # Map: bob_id -> bob instance

# different entities that Bob could be - Doctor should always be in index 0
ID_PREFIXES = ['Doctor', 'Cardiologist', 'Nutritionist', 'Nurse', 'Dietitian']

key_gen = DemoKeyGenerator(KEYS_FOLDER)

#############
# UI Layout #
#############


def get_layout(first_bob: bool):
    prefix = ID_PREFIXES[0]
    if not first_bob:
        # prefix from random index in prefixes list
        index = random.randint(0, (len(ID_PREFIXES) - 1))
        prefix = ID_PREFIXES[index]

    unique_id = f'{prefix}-{os.urandom(4).hex()}'

    # create bob instance
    bob = _create_bob(unique_id)
    bob_instances[unique_id] = bob  # add bob instance to dict
    print(f'Initializing UI for Bob (id:{unique_id}) = {bob}')

    # generate ui layout
    layout = html.Div([
        html.Div([
            html.Img(src='/assets/nucypher_logo.png'),
        ], className='banner'),
        html.Div([
            html.Div([
                html.Div([
                    html.Img(src='/assets/bob.png'),
                ], className='two columns'),
                html.Div([
                    html.Div([
                        html.H2(f'{prefix.upper()} BOB'),
                        html.P(
                            f'{prefix} Bob is the {prefix} who Alicia will grant access to her encrypted heart rate '
                            f'measurements (which was populated by the Heart Monitor) and requests '
                            f'a re-encrypted ciphertext for each measurement, which can then be decrypted '
                            f'using their private key.'),
                    ], className="row")
                ], className='five columns'),
            ], className='row'),
        ], className='app_name'),
        html.Hr(),
        html.Div([
            html.H3('Properties'),
            html.Div([
                html.Div('Unique Bob Id:', className='two columns'),
                html.Div(id='bob-unique-id', children='{}'.format(unique_id), className='two columns'),
            ], className='row'),
            html.Br(),
            html.Button('Get Keys',
                        id='get-keys-button',
                        type='submit',
                        className='button button-primary'),
            html.Div(id='pub-keys', className='row'),
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


def _create_bob(unique_id: str) -> Bob:
    # TODO: path joins?
    temp_bob_dir = os.path.join(BOB_FOLDER, f'bob-{unique_id}-files')

    temp_ursula_certificate_dir = os.path.join(temp_bob_dir, 'ursula-certs')
    temp_bob_certificate_dir = os.path.join(temp_bob_dir, 'bob-certs')

    # Ensure previous demo files removed, then create new ones
    shutil.rmtree(temp_bob_dir, ignore_errors=True)
    os.mkdir(temp_bob_dir)
    os.mkdir(temp_ursula_certificate_dir)
    os.mkdir(temp_bob_certificate_dir)

    network_middleware = None
    if 'TEST_HEARTBEAT_DEMO_UI_SEEDNODE_PORT' in os.environ:
        network_middleware = MockRestMiddleware()  # use of federated_ursulas for unit tests
    ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URL,
                                             federated_only=True,
                                             network_middleware=network_middleware,
                                             minimum_stake=0)

    bob_privkeys = key_gen.get_recipient_privkeys(unique_id)

    bob_enc_keypair = DecryptingKeypair(private_key=bob_privkeys["enc"])
    bob_sig_keypair = SigningKeypair(private_key=bob_privkeys["sig"])
    enc_power = DecryptingPower(keypair=bob_enc_keypair)
    sig_power = SigningPower(keypair=bob_sig_keypair)
    power_ups = [enc_power, sig_power]

    print('Creating Bob with id: {}...'.format(unique_id))

    network_middleware = RestMiddleware()
    if 'TEST_HEARTBEAT_DEMO_UI_SEEDNODE_PORT' in os.environ:
        network_middleware = MockRestMiddleware()  # use of federated_ursulas for unit tests
    bob = Bob(
        is_me=True,
        federated_only=True,
        crypto_power_ups=power_ups,
        start_learning_now=True,
        abort_on_learning_error=True,
        known_nodes=[ursula],
        save_metadata=False,
        network_middleware=network_middleware,
    )

    return bob


#################
# Bob's Actions #
#################

policy_joined = dict()  # Map: bob_id -> policy_label


@app.callback(
    Output('pub-keys', 'children'),
    [],
    [State('bob-unique-id', 'children')],
    [Event('get-keys-button', 'click')]
)
def get_doctor_pubkeys(bob_id):
    bob_pubkeys = key_gen.get_recipient_pubkeys(bob_id)
    return html.Div([
        html.Div([
            html.Div('Verifying Key (hex):', className='two columns'),
            html.Div('{}'.format(bob_pubkeys[VERIFYING_KEY].to_bytes().hex()), className='seven columns')
        ], className='row'),
        html.Div([
            html.Div('Encrypting Key (hex):', className='two columns'),
            html.Div('{}'.format(bob_pubkeys[ENCRYPTING_KEY].to_bytes().hex()), className='seven columns'),
        ], className='row')
    ])


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

    # get bob instance
    bob = bob_instances[bob_id]

    bob_enc_key = key_gen.get_recipient_pubkeys(bob_id)[ENCRYPTING_KEY]

    # Let's join the policy generated by Alicia. We just need some info about it.
    try:
        with open(POLICY_INFO_FILE.format(bob_enc_key.to_bytes().hex()), 'r') as f:
            policy_data = json.load(f)
    except FileNotFoundError:
        print("No policy file available")
        return ACCESS_DISALLOWED

    policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data['policy_encrypting_key']))
    alice_sig_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data['alice_verifying_key']))
    label = policy_data['label']

    if bob_id not in policy_joined:
        bob.join_policy(label.encode(), alice_sig_key)
        print(f'Bob (id:{bob_id}) joined policy with label "{label}" '
              f'and encrypting key "{policy_data["policy_encrypting_key"]}"')
        policy_joined[bob_id] = label

    with open(DATA_SOURCE_INFO_FILE, "rb") as file:
        data_source_metadata = msgpack.load(file, raw=False)

    cached_hb_values = collections.OrderedDict()
    if (json_latest_values is not None) and (json_latest_values != ACCESS_DISALLOWED):
        cached_hb_values = json.loads(json_latest_values, object_pairs_hook=collections.OrderedDict)

    last_timestamp = time.time() - 5  # last 5s
    if len(cached_hb_values) > 0:
        # use last timestamp
        last_timestamp = list(cached_hb_values.keys())[-1]

    # Bob also needs to create a view of the Data Source from its public keys
    # The doctor also needs to create a view of the Data Source from its public keys
    data_source = Enrico.from_public_keys(
        {SigningPower: data_source_metadata['data_source_verifying_key']},
        policy_encrypting_key=policy_encrypting_key
    )

    db_conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query(f'SELECT Timestamp, EncryptedData '
                               f'FROM {DB_NAME} '
                               f'WHERE Timestamp > "{last_timestamp}" '
                               f'ORDER BY Timestamp;',
                               db_conn)

        for index, row in df.iterrows():
            kit_bytes = bytes.fromhex(row['EncryptedData'])
            message_kit = UmbralMessageKit.from_bytes(kit_bytes)

            # Now he can ask the NuCypher network to get a re-encrypted version of each MessageKit.
            try:
                retrieved_plaintexts = bob.retrieve(
                    message_kit=message_kit,
                    data_source=data_source,
                    alice_verifying_key=alice_sig_key,
                    label=label.encode()
                )

                hb = msgpack.loads(retrieved_plaintexts[0], raw=False)
                timestamp = row['Timestamp']
                cached_hb_values[timestamp] = hb
            except Ursula.NotEnoughUrsulas as e:
                # we can ignore
                print(e)
                continue
            except Exception as e:
                # for the demo, this happens when bob's access is revoked
                traceback.print_exc()
                policy_joined.pop(bob_id, None)
                return ACCESS_DISALLOWED
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

    if json_cached_readings == ACCESS_DISALLOWED:
        return html.Div('WARNING: Your access has either not been granted or has been revoked!', style={'color': 'red'})

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
