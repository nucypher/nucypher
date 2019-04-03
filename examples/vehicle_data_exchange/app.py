import dash
import os
import shutil
from examples.vehicle_data_exchange.demo_keys import KEYS_FOLDER

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Vehicular Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True

# remove old key files and re-create folder
shutil.rmtree(KEYS_FOLDER, ignore_errors=True)
os.mkdir(KEYS_FOLDER)

# remove old data files and re-create data folder
DATA_FOLDER = f'{os.path.dirname(os.path.abspath(__file__))}/data'
shutil.rmtree(DATA_FOLDER, ignore_errors=True)
os.mkdir(DATA_FOLDER)

DB_FILE = f'{DATA_FOLDER}/vehicle_sensors.db'
DB_NAME = 'VehicleData'

# OBD properties
PROPERTIES = {
    'engineOn': 'Engine Status',
    'temp': 'Temperature (°C)',
    'rpm': 'Revolutions Per Minute',
    'vss': 'Vehicle Speed',
    'maf': 'Mass AirFlow',
    'throttlepos': 'Throttle Position (%)',
    'lat': 'Latitude (°)',
    'lon': 'Longitude (°)',
    'alt': 'Alternator Voltage',
    'gpsSpeed': 'GPS Speed',
    'course': 'Course',
    'gpsTime': "GPS Timestamp"
}

# create shared folder for data shared between characters
SHARED_FOLDER = f'{os.path.dirname(os.path.abspath(__file__))}/shared'
shutil.rmtree(SHARED_FOLDER, ignore_errors=True)
os.mkdir(SHARED_FOLDER)

# policy information
POLICY_INFO_FILE = os.path.join(SHARED_FOLDER, "policy_metadata.{}.json")

DATA_SOURCE_INFO_FILE = os.path.join(SHARED_FOLDER, 'data_source.msgpack')

# remove old bob-files
BOB_FILES = f'{os.path.dirname(os.path.abspath(__file__))}/bob-files'
shutil.rmtree(BOB_FILES, ignore_errors=True)
os.mkdir(BOB_FILES)

# We expect the url of the seednode to be local
port = os.getenv("TEST_VEHICLE_DATA_EXCHANGE_SEEDNODE_PORT")   # port used for unit test
if port is None:
    port = '11500'  # default local ursula
SEEDNODE_URL = f'localhost:{port}'
