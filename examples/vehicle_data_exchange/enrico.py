import json
import random
import sqlite3
import time

import dash_core_components as dcc
import dash_html_components as html
import dash_table
import msgpack
import pandas as pd
from dash.dependencies import Output, Input, State, Event
from umbral.keys import UmbralPublicKey

from examples.vehicle_data_exchange.app import app, DB_FILE, DB_NAME, DATA_SOURCE_INFO_FILE
from nucypher.characters.lawful import Enrico

cached_data_source = list()

layout = html.Div([
    html.Div([
        html.Img(src='/assets/nucypher_logo.png'),
    ], className='banner'),
    html.Div([
        html.Div([
            html.Div([
                html.Img(src='/assets/enrico_obd.png', style={'height': '150px', 'width': '220px'}),
            ], className='two columns'),
            html.Div([
                html.Div([
                    html.H2('ENRICO'),
                    html.P("Enrico is the OBD device in Alicia's vehicle that uses a data policy key "
                           "to encrypt Alicia's vehicular measurements into a database or some storage service "
                           "(e.g., IPFS, S3, whatever). Data Sources like the OBD device remain "
                           "completely unaware of the recipients. In their mind, they are producing data "
                           "for Alicia. "),
                ], className="row")
            ], className='five columns'),
        ], className='row'),
    ], className='app_name'),
    html.Hr(),
    html.H3('Data Policy'),
    html.Div([
        html.Div([
            html.Div('Policy Encrypting Key (hex): ', className='two columns'),
            dcc.Input(id='policy-enc-key', type='text', className='seven columns'),
        ], className='row'),
        html.Button('Start Monitoring', id='generate-button', type='submit',
                    className="button button-primary", n_clicks_timestamp='0'),
        dcc.Interval(id='gen-measurements-update', interval=1000, n_intervals=0),
    ], className='row'),
    html.Hr(),
    html.Div([
        html.H3('Encrypted OBD Data in Database'),
        html.Div([
            html.Div('Latest Vehicle Data: ', className='two columns'),
            html.Div(id='cached-last-readings', className='two columns'),
        ], className='row'),
        html.Br(),
        html.H5('Last 30s of Data: '),
        html.Div(id='db-table-content'),
    ], className='row'),
])


@app.callback(
    Output('cached-last-readings', 'children'),
    [],
    [State('generate-button', 'n_clicks_timestamp'),
     State('policy-enc-key', 'value'),
     State('cached-last-readings', 'children')],
    [Event('gen-measurements-update', 'interval'),
     Event('generate-button', 'click')]
)
def generate_vehicular_data(gen_time, policy_enc_key_hex, cached_last_reading):
    if int(gen_time) == 0:
        # button has not been clicked as yet or interval triggered before click
        return None

    policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_enc_key_hex))
    if not cached_data_source:
        data_source = Enrico(policy_encrypting_key=policy_encrypting_key)
        data_source_verifying_key = bytes(data_source.stamp)

        data = {
            'data_source_verifying_key': data_source_verifying_key,
        }
        with open(DATA_SOURCE_INFO_FILE, "wb") as file:
            msgpack.dump(data, file, use_bin_type=True)

        cached_data_source.append(data_source)
    else:
        data_source = cached_data_source[0]

    latest_reading = generate_new_reading(cached_last_reading)

    plaintext = msgpack.dumps(latest_reading, use_bin_type=True)
    message_kit, _signature = data_source.encrypt_message(plaintext)
    kit_bytes = message_kit.to_bytes()

    timestamp = time.time()
    df = pd.DataFrame.from_dict({
        'Timestamp': [timestamp],
        'EncryptedData': [kit_bytes.hex()],
    })

    # add new vehicle data
    db_conn = sqlite3.connect(DB_FILE)
    try:
        df.to_sql(name=DB_NAME, con=db_conn, index=False, if_exists='append')
        print(f'Added vehicle sensor readings to db: {timestamp} -> {latest_reading}')
    finally:
        db_conn.close()

    return json.dumps(latest_reading)


@app.callback(
    Output('db-table-content', 'children'),
    [Input('cached-last-readings', 'children')]
)
def display_vehicular_data(cached_last_reading):
    if cached_last_reading is None:
        # button hasn't been clicked as yet
        return ''

    now = time.time()
    duration = 30  # last 30s of readings
    db_conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query(f'SELECT Timestamp, EncryptedData '
                               f'FROM {DB_NAME} '
                               f'WHERE Timestamp > "{now - duration}" AND Timestamp <= "{now}" '
                               f'ORDER BY Timestamp DESC;',
                               db_conn)
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


def generate_new_reading(cached_last_reading) -> dict:
    car_data = dict()
    sensor_readings = dict()
    car_data['carInfo'] = sensor_readings

    if cached_last_reading is None:
        # generate readings
        sensor_readings['engineOn'] = True
        sensor_readings['temp'] = random.randrange(180, 230)
        sensor_readings['rpm'] = random.randrange(1000, 7500)
        sensor_readings['vss'] = random.randrange(10, 80)
        sensor_readings['maf'] = random.randrange(10, 20)
        sensor_readings['throttlepos'] = random.randrange(10, 90)
        sensor_readings['lat'] = random.randrange(30, 40)
        sensor_readings['lon'] = random.randrange(-100, -80)
        sensor_readings['alt'] = random.randrange(40, 50)
        sensor_readings['gpsSpeed'] = random.randrange(30, 140)
        sensor_readings['course'] = random.randrange(100, 180)
        sensor_readings['gpsTime'] = time.time()
    else:
        last_sensor_readings = json.loads(cached_last_reading)['carInfo']
        for key in last_sensor_readings.keys():
            if key in ['engineOn']:
                # skip boolean value
                sensor_readings['engineOn'] = last_sensor_readings[key]
            else:
                # modify reading based on prior value
                sensor_readings[key] = last_sensor_readings[key] + random.uniform(-1, 1)

    return car_data
