import datetime
import json
import os

import dash_core_components as dcc
import dash_html_components as html
import maya
from dash.dependencies import Output, Input, State, Event
from twisted.logger import globalLogPublisher
from umbral.keys import UmbralPublicKey

from examples.heartbeat_demo.ui.app import app, SEEDNODE_URL, POLICY_INFO_FILE, ALICIA_FOLDER
from nucypher.characters.lawful import Bob, Ursula
from nucypher.config.characters import AliceConfiguration
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.utilities.logging import SimpleObserver
from nucypher.utilities.sandbox.middleware import MockRestMiddleware

######################
# Boring setup stuff #
######################
#
# # Twisted Logger
globalLogPublisher.addObserver(SimpleObserver())
#
# # Temporary file storage
TEMP_URSULA_CERTIFICATE_DIR = os.path.join(ALICIA_FOLDER, 'ursula-certs')

#######################################
# Alicia, the Authority of the Policy #
#######################################

passphrase = "TEST_ALICIA_INSECURE_DEVELOPMENT_PASSWORD"
# Remove previous demo files and create new ones
os.mkdir(TEMP_URSULA_CERTIFICATE_DIR)

network_middleware = None
if 'TEST_HEARTBEAT_DEMO_UI_SEEDNODE_PORT' in os.environ:
    network_middleware = MockRestMiddleware()  # use of federated_ursulas for unit tests
ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URL,
                                         federated_only=True,
                                         network_middleware=network_middleware,
                                         minimum_stake=0)

network_middleware = None
if 'TEST_HEARTBEAT_DEMO_UI_SEEDNODE_PORT' in os.environ:
    network_middleware = MockRestMiddleware()  # use of federated_ursulas for unit tests
alice_config = AliceConfiguration(
    config_root=os.path.join(ALICIA_FOLDER, "config_root"),
    is_me=True,
    known_nodes={ursula},
    start_learning_now=False,
    federated_only=True,
    network_middleware=network_middleware,
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
        html.Img(src='/assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.Div([
            html.Div([
                html.Img(src='/assets/alicia.png'),
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
                    className='button button-primary', n_clicks_timestamp='0'),
        html.Div([
            html.Div([
                html.Div('Policy Label:', className='two columns'),
                html.Div(id='policy-label', className='two columns'),
            ], className='row'),
            html.Div([
                html.Div('Policy Encrypting Key (hex):', className='two columns'),
                html.Div(id='policy-enc-key', className='seven columns')
            ], className='row')
        ]),
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
            html.Div('Recipient Verifying Key (hex): ', className='two columns'),
            dcc.Input(id='recipient-sig-key-grant', type='text', className='seven columns')
        ], className='row'),
        html.Div([
            html.Div('Recipient Encrypting Key (hex): ', className='two columns'),
            dcc.Input(id='recipient-enc-key-grant', type='text', className='seven columns'),
        ], className='row'),
        html.Div([
            html.Button('Grant Access', id='grant-button', type='submit',
                        className='button button-primary', n_clicks_timestamp='0'),
            html.Div(id='grant-response'),
        ], className='row'),
        html.Br(),
        html.Div([
            html.Div('Revoke Recipient Encrypting Key (hex): ', className='two columns'),
            dcc.Input(id='recipient-enc-key-revoke', type='text', className='seven columns'),
        ], className='row'),
        html.Div([
            html.Button('Revoke Access', id='revoke-button', type='submit',
                        className='button button-primary', n_clicks_timestamp='0'),
            html.Div(id='revoke-response', style={'color': 'red'}),
        ], className='row')
    ])
])

# store and track policies pub_key_hex -> policy
granted_policies = dict()


@app.callback(
    Output('policy-label', 'children'),
    events=[Event('create-policy-button', 'click')]
)
def create_policy_label():
    label = f'heart-data-{os.urandom(4).hex()}'
    return label


@app.callback(
    Output('policy-enc-key', 'children'),
    [Input('policy-label', 'children')],
)
def create_policy_key(policy_label):
    if policy_label is not None:
        policy_encrypting_key = alicia.get_policy_pubkey_from_label(policy_label.encode())
        return policy_encrypting_key.to_bytes().hex()

    return ''


@app.callback(
    Output('grant-response', 'children'),
    [],
    [State('revoke-button', 'n_clicks_timestamp'),
     State('grant-button', 'n_clicks_timestamp'),
     State('policy-label', 'children'),
     State('days', 'value'),
     State('m-value', 'value'),
     State('n-value', 'value'),
     State('recipient-enc-key-grant', 'value'),
     State('recipient-sig-key-grant', 'value')],
    [Event('grant-button', 'click'),
     Event('revoke-button', 'click')]
)
def grant_access(revoke_time, grant_time, policy_label, days, m, n, recipient_enc_key_hex, recipient_sig_key_hex):
    if policy_label is None:
        # policy not yet created so can't grant access
        return ''
    if int(revoke_time) >= int(grant_time):
        # either triggered at start or because revoke was executed
        return ''

    # Alicia now wants to share data associated with this label.
    # To do so, she needs the public key of the recipient.
    enc_key = UmbralPublicKey.from_bytes(bytes.fromhex(recipient_enc_key_hex))
    sig_key = UmbralPublicKey.from_bytes(bytes.fromhex(recipient_sig_key_hex))

    powers_and_material = {
        DecryptingPower: enc_key,
        SigningPower: sig_key
    }

    # We create a view of the Bob who's going to be granted access.
    bob = Bob.from_public_keys(powers_and_material=powers_and_material,
                               federated_only=True)

    # Here are our remaining Policy details, such as:
    # - Policy duration
    policy_end_datetime = maya.now() + datetime.timedelta(days=int(days))

    # - m-out-of-n: This means Alicia splits the re-encryption key in 5 pieces and
    #               she requires Bob to seek collaboration of at least 3 Ursulas
    # With this information, Alicia creates a policy granting access to Bob.
    # The policy is sent to the NuCypher network.
    print(f'Creating access to policy {policy_label} for the Bob with public key {recipient_enc_key_hex}...')
    policy = alicia.grant(bob=bob,
                          label=policy_label.encode(),
                          m=int(m),
                          n=int(n),
                          expiration=policy_end_datetime)
    print("Done!")

    # For the demo, we need a way to share with Bob some additional info
    # about the policy, so we store it in a JSON file
    policy_info = {
        "policy_encrypting_key": policy.public_key.to_bytes().hex(),
        "alice_verifying_key": bytes(alicia.stamp).hex(),
        "label": policy_label,
    }

    print("policy file", POLICY_INFO_FILE.format(recipient_enc_key_hex))
    with open(POLICY_INFO_FILE.format(recipient_enc_key_hex), 'w') as f:
        json.dump(policy_info, f)

    granted_policies[recipient_enc_key_hex] = policy

    return f'Access to policy {policy_label} granted to recipient with encrypting key: {recipient_enc_key_hex}!'


@app.callback(
    Output('revoke-response', 'children'),
    [Input('grant-button', 'n_clicks_timestamp')],
    [State('revoke-button', 'n_clicks_timestamp'),
     State('recipient-enc-key-revoke', 'value')],
    [Event('revoke-button', 'click'),
     Event('grant-button', 'click')]
)
def revoke_access(grant_time, revoke_time, recipient_enc_key_hex):
    if int(grant_time) >= int(revoke_time):
        # either triggered at start or because grant was executed
        return ''

    policy = granted_policies.pop(recipient_enc_key_hex, None)
    if policy is None:
        return f'Policy has not been previously granted for recipient with public key {recipient_enc_key_hex}'

    print("Revoking access to recipient", recipient_enc_key_hex)
    try:
        failed_revocations = alicia.revoke(policy=policy)
        if failed_revocations:
            return f'WARNING: Access revoked to recipient with public key {recipient_enc_key_hex} ' \
                   f'- but {len(failed_revocations)} nodes failed to revoke'

        return f'Access revoked to recipient with public key {recipient_enc_key_hex}!'
    finally:
        os.remove(POLICY_INFO_FILE.format(recipient_enc_key_hex))
