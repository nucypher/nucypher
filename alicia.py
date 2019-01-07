import dash_core_components as dcc
from dash.dependencies import Output, Input, State, Event
import dash_html_components as html
import demo_keys
import os
from umbral import config, signing
from umbral.keys import UmbralPublicKey

from app import app

layout = html.Div([
    html.Div([
        html.Img(src='./assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.H2('ALICIA'),
        html.P('<blurb about Alicia>')
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
            dcc.Input(id='m-value', value='2', type='number', className='two columns'),
        ], className='row'),
        html.Div([
            html.Div('N-Shares: ', className='two columns'),
            dcc.Input(id='n-value', value='3', type='number', className='two columns'),
        ], className='row'),
        html.Div([
            html.Div('Recipient Public Key: ', className='two columns'),
            dcc.Input(id='recipient-pub-key', type='text', className='seven columns'),
        ], className='row'),
        html.Div([
            html.Button('Grant Access', id='grant-button', type='submit',
                        className='button button-primary', n_clicks_timestamp='0'),
            html.Div(id='grant-response'),
        ], className='row'),
        html.Br(),
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
    label = 'heart-data-❤️-' + os.urandom(4).hex()
    label = label.encode()

    policy_pubkey = demo_keys.get_alicia_pubkeys()['enc']

    return "The policy public key for " \
           "label '{}' is {}".format(label.decode('utf-8'), policy_pubkey.to_bytes().hex())


@app.callback(
    Output('grant-response', 'children'),
    [Input('revoke-button', 'n_clicks_timestamp')],
    [State('grant-button', 'n_clicks_timestamp'),
     State('days', 'value'),
     State('m-value', 'value'),
     State('n-value', 'value'),
     State('recipient-pub-key', 'value')],
    [Event('grant-button', 'click'),
     Event('revoke-button', 'click')]
)
def grant_access(revoke_time, grant_time, days, m, n, recipient_pubkey_hex):
    if int(revoke_time) >= int(grant_time):
        # either triggered at start or because revoke was executed
        return ''

    try:
        # set default curve, if not set already
        config.set_default_curve()
    except RuntimeError:
        pass

    # obtain keys for Alicia
    alicia_priv_keys = demo_keys.get_alicia_privkeys()
    alicia_signer = signing.Signer(private_key=alicia_priv_keys['sig'])

    # create Umbral key for recipient
    recipient_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(recipient_pubkey_hex))

    import nucypher_helper
    nucypher_helper.grant_access_policy(alicia_priv_keys['enc'],
                                        alicia_signer,
                                        recipient_pubkey,
                                        int(m),
                                        int(n))

    return 'Access granted to recipient with public key: {}!'.format(recipient_pubkey_hex)


@app.callback(
    Output('revoke-response', 'children'),
    [Input('grant-button', 'n_clicks_timestamp')],
    [State('revoke-button', 'n_clicks_timestamp')],
    [Event('revoke-button', 'click'),
     Event('grant-button', 'click')]
)
def revoke_access(grant_time, revoke_time):
    if int(grant_time) >= int(revoke_time):
        # either triggered at start or because grant was executed
        return ''

    # TODO: implement revocation
    return 'Access revoked to recipient! - Not implemented as yet'
