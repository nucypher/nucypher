import dash_core_components as dcc
from dash.dependencies import Output, Input, State, Event
import dash_html_components as html
import demo_keys
import os

from app import app, SHARED_FOLDER

from nucypher.characters.lawful import Bob, Ursula
from nucypher.config.characters import AliceConfiguration
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import SimpleObserver

import datetime
import shutil
import maya
import json
from twisted.logger import globalLogPublisher

POLICY_INFO_FILE = os.path.join(SHARED_FOLDER, "policy_metadata.json")

######################
# Boring setup stuff #
######################
#
# # Twisted Logger
globalLogPublisher.addObserver(SimpleObserver())
#
# # Temporary file storage
TEMP_ALICE_DIR = "{}/alicia-files".format(os.path.dirname(os.path.abspath(__file__)))
TEMP_URSULA_CERTIFICATE_DIR = "{}/ursula-certs".format(TEMP_ALICE_DIR)

# We expect the url of the seednode as the first argument.
SEEDNODE_URL = "127.0.0.1:10151"

#######################################
# Alicia, the Authority of the Policy #
#######################################


# We get a persistent Alice.
passphrase = "TEST_ALICIA_INSECURE_DEVELOPMENT_PASSWORD"
try:  # If we had an existing Alicia in disk, let's get it from there
    alice_config_file = os.path.join(TEMP_ALICE_DIR, "config_root", "alice.config")
    new_alice_config = AliceConfiguration.from_configuration_file(
        filepath=alice_config_file,
        network_middleware=RestMiddleware(),
        start_learning_now=False,
        save_metadata=False,
    )
    alicia = new_alice_config(passphrase=passphrase)
except:  # If anything fails, let's create Alicia from scratch
    # Remove previous demo files and create new ones
    shutil.rmtree(TEMP_ALICE_DIR, ignore_errors=True)
    os.mkdir(TEMP_ALICE_DIR)
    os.mkdir(TEMP_URSULA_CERTIFICATE_DIR)

    ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URL,
                                             federated_only=True,
                                             minimum_stake=0)

    alice_config = AliceConfiguration(
        config_root=os.path.join(TEMP_ALICE_DIR, "config_root"),
        is_me=True,
        known_nodes={ursula},
        start_learning_now=False,
        federated_only=True,
        learn_on_same_thread=True,
    )
    alice_config.initialize(password=passphrase)
    alice_config.keyring.unlock(password=passphrase)
    alicia = alice_config.produce()

    # We will save Alicia's config to a file for later use
    alice_config_file = alice_config.to_configuration_file()

# Let's get to learn about the NuCypher network
alicia.start_learning_loop(now=True)


layout = html.Div([
    html.Div([
        html.Img(src='./assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.Div([
            html.Div([
                html.Img(src='./assets/alicia.png'),
            ], className='two columns'),
            html.Div([
                html.Div([
                    html.H2('ALICIA'),
                    html.P('Alicia has a Heart Monitor device (Enrico) that measures her heart '
                           'rate and outputs this data in encrypted form. She thinks that at some '
                           'point in the future she may want to share this data with her doctor.')
                ], className="row")
            ], className='five columns'),
        ], className='row'),
    ], className='app_name'),
    html.Hr(),
    html.Div([
        html.H3('Policy Key'),
        html.Button('Create Policy Key', id='create-policy-button', type='submit',
                    className='button button-primary'),
        html.Div(id='policy-key-response')
    ], className='row'),
    html.Hr(),
    html.Div([
        html.H3('Access Policy'),
        html.Div([
            html.Div('Policy Duration (Days): ', className='two columns'),
            dcc.Input(id='days', value='5', type='number', className='two columns'),
        ], className='row'),
        html.Div([
            html.Div('M-Threshold: ', className='two columns'),
            dcc.Input(id='m-value', value='1', type='number', className='two columns'),
        ], className='row'),
        html.Div([
            html.Div('N-Shares: ', className='two columns'),
            dcc.Input(id='n-value', value='1', type='number', className='two columns'),
        ], className='row'),
        html.Div([
            html.Div('Grant Recipient Public Key: ', className='two columns'),
            dcc.Input(id='recipient-pub-key-grant', type='text', className='seven columns'),
        ], className='row'),
        html.Div([
            html.Button('Grant Access', id='grant-button', type='submit',
                        className='button button-primary', n_clicks_timestamp='0'),
            html.Div(id='grant-response'),
        ], className='row'),
        html.Br(),
        html.Div([
            html.Div('Revoke Recipient Public Key: ', className='two columns'),
            dcc.Input(id='recipient-pub-key-revoke', type='text', className='seven columns'),
        ], className='row'),
        html.Div([
            html.Button('Revoke Access', id='revoke-button', type='submit',
                        className='button button-primary', n_clicks_timestamp='0'),
            html.Div(id='revoke-response', style={'color': 'red'}),
        ], className='row')
    ])
])


@app.callback(
    Output('policy-key-response', 'children'),
    events=[Event('create-policy-button', 'click')]
)
def create_policy():
    label = 'heart-data'
    label = label.encode()

    policy_pubkey = alicia.get_policy_pubkey_from_label(label)

    return "The policy public key for " \
           "label '{}' is {}".format(label.decode('utf-8'), policy_pubkey.to_bytes().hex())


@app.callback(
    Output('grant-response', 'children'),
    [Input('revoke-button', 'n_clicks_timestamp')],
    [State('grant-button', 'n_clicks_timestamp'),
     State('days', 'value'),
     State('m-value', 'value'),
     State('n-value', 'value'),
     State('recipient-pub-key-grant', 'value')],
    [Event('grant-button', 'click'),
     Event('revoke-button', 'click')]
)
def grant_access(revoke_time, grant_time, days, m, n, recipient_pubkey_hex):
    if int(revoke_time) >= int(grant_time):
        # either triggered at start or because revoke was executed
        return ''

    label = b'heart-data'

    # Alicia now wants to share data associated with this label.
    # To do so, she needs the public key of the recipient.
    # In this example, we generate it on the fly (for demonstration purposes)
    bob_pubkeys = demo_keys.get_recipient_pubkeys("bob")

    powers_and_material = {
        DecryptingPower: bob_pubkeys['enc'],
        SigningPower: bob_pubkeys['sig']
    }

    # We create a view of the Bob who's going to be granted access.
    bob = Bob.from_public_keys(powers_and_material=powers_and_material,
                               federated_only=True)

    # Here are our remaining Policy details, such as:
    # - Policy duration
    policy_end_datetime = maya.now() + datetime.timedelta(days=int(days))
    # - m-out-of-n: This means Alicia splits the re-encryption key in 5 pieces and
    #               she requires Bob to seek collaboration of at least 3 Ursulas
    # TODO: Let's put just one Ursula for the moment.
    m, n = 1, 1

    # With this information, Alicia creates a policy granting access to Bob.
    # The policy is sent to the NuCypher network.
    print("Creating access policy for the Doctor...")
    policy = alicia.grant(bob=bob,
                          label=label,
                          m=int(m),
                          n=int(n),
                          expiration=policy_end_datetime)
    print("Done!")

    # For the demo, we need a way to share with Bob some additional info
    # about the policy, so we store it in a JSON file
    policy_info = {
        "policy_pubkey": policy.public_key.to_bytes().hex(),
        "alice_sig_pubkey": bytes(alicia.stamp).hex(),
        "label": label.decode("utf-8"),
    }

    with open(POLICY_INFO_FILE, 'w') as f:
        json.dump(policy_info, f)

    return 'Access granted to recipient with public key: {}!'.format(recipient_pubkey_hex)


@app.callback(
    Output('revoke-response', 'children'),
    [Input('grant-button', 'n_clicks_timestamp')],
    [State('revoke-button', 'n_clicks_timestamp'),
     State('recipient-pub-key-revoke', 'value')],
    [Event('revoke-button', 'click'),
     Event('grant-button', 'click')]
)
def revoke_access(grant_time, revoke_time, recipient_pubkey_hex):
    if int(grant_time) >= int(revoke_time):
        # either triggered at start or because grant was executed
        return ''

    return 'Access revoked to recipient with public key {}! - Not implemented as yet'.format(recipient_pubkey_hex)
