import dash_core_components as dcc
from dash.dependencies import Output, Input, State, Event
import dash_html_components as html
import os

from examples.heartbeat_rest_ui.app import app, POLICY_INFO_FILE

import datetime
import maya
import json
import requests

ALICE_URL = "http://localhost:8151"


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
            dcc.Input(id='recipient-sig-key-grant', type='text', className='seven columns'),
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
            html.Div('Revoke Recipient Encrypting Key: ', className='two columns'),
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

        # Obtain policy public key based on label from alicia character control REST endpoint
        response = requests.post(f'{ALICE_URL}/derive_policy_encrypting_key/{policy_label}')

        if response.status_code != 200:
            print(f'> ERROR: Problem obtaining policy public key; status code = {response.status_code}; '
                  f'response = {response.content}')
            return f'> ERROR: Problem obtaining policy public key; status code = {response.status_code}'

        response_data = json.loads(response.content)
        return response_data['result']['policy_encrypting_key']

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
     State('recipient-sig-key-grant', 'value'),
     State('recipient-enc-key-grant', 'value')],
    [Event('grant-button', 'click'),
     Event('revoke-button', 'click')]
)
def grant_access(revoke_time, grant_time, policy_label, days, m, n, recipient_sig_key_hex, recipient_enc_key_hex):
    if policy_label is None:
        # policy not yet created so can't grant access
        return ''
    if int(revoke_time) >= int(grant_time):
        # either triggered at start or because revoke was executed
        return ''

    # expiration time of policy
    policy_end_datetime = maya.now() + datetime.timedelta(days=int(days))

    # - m-out-of-n: This means Alicia splits the re-encryption key in 5 pieces and
    #               she requires Bob to seek collaboration of at least 3 Ursulas
    request_data = {
        'bob_encrypting_key': recipient_enc_key_hex,
        'bob_verifying_key': recipient_sig_key_hex,
        'm': int(m),
        'n': int(n),
        'label': policy_label,
        'expiration': policy_end_datetime.iso8601(),
    }

    # With this information, Alicia creates a policy granting access to Bob.
    # The policy is sent to the NuCypher network via the character control REST endpoint for alicia
    print(f'Creating access to policy {policy_label} for the Bob with public key {recipient_enc_key_hex}...')

    response = requests.put(f'{ALICE_URL}/grant', data=json.dumps(request_data))

    if response.status_code != 200:
        print(f'> ERROR: Problem granting access to recipient with public key {recipient_enc_key_hex} '
              f'for policy {policy_label} ; status code = {response.status_code}; response = {response.content}')
        return f'> ERROR: Problem granting access to recipient with public key {recipient_enc_key_hex} for ' \
               f'policy {policy_label} ; status code = {response.status_code};'

    print("Done!")

    response_data = json.loads(response.content)
    alice_verifying_key = response_data['result']['alice_verifying_key']
    policy_enc_key = response_data['result']['policy_encrypting_key']

    # For the demo, we need a way to share with Bob some additional info
    # about the policy, so we store it in a JSON file
    policy_info = {
        "policy_encrypting_key": policy_enc_key,
        "alice_verifying_key": alice_verifying_key,
        "label": policy_label,
    }

    print("policy file", POLICY_INFO_FILE.format(recipient_enc_key_hex))
    with open(POLICY_INFO_FILE.format(recipient_enc_key_hex), 'w') as f:
        json.dump(policy_info, f)

    granted_policies[recipient_enc_key_hex] = policy_label

    return f'Access to policy {policy_label} granted to recipient with encryption public key: {recipient_enc_key_hex}!'


@app.callback(
    Output('revoke-response', 'children'),
    [Input('grant-button', 'n_clicks_timestamp')],
    [State('revoke-button', 'n_clicks_timestamp'),
     State('recipient-enc-key-revoke', 'value')],
    [Event('revoke-button', 'click'),
     Event('grant-button', 'click')]
)
def revoke_access(grant_time, revoke_time, recipient_pubkey_hex):
    if int(grant_time) >= int(revoke_time):
        # either triggered at start or because grant was executed
        return ''

    return f'Access revoked to recipient with public key {recipient_pubkey_hex}! - Not implemented as yet'

    # TODO: revocation is not yet available via the character control; below is how it would be done with the python API
    # policy = granted_policies.pop(recipient_pubkey_hex, None)
    # if policy is None:
    #     return 'Policy has not been previously granted for recipient with public key {}'.format(recipient_pubkey_hex)
    #
    # print("Revoking access to recipient", recipient_pubkey_hex)
    # try:
    #     failed_revocations = alicia.revoke(policy=policy)
    #     if failed_revocations:
    #         return 'WARNING: Access revoked to recipient with public key {} - but {} nodes failed to revoke'\
    #             .format(recipient_pubkey_hex, len(failed_revocations))
    #
    #     return 'Access revoked to recipient with public key {}!'.format(recipient_pubkey_hex)
    # finally:
    #     os.remove(POLICY_INFO_FILE.format(recipient_pubkey_hex))
