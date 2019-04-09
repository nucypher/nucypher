import dash
import os
import shutil

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Vehicular Data Sharing Application",
                external_stylesheets=external_stylesheets,
                assets_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets'),
                suppress_callback_exceptions=True)
server = app.server

# key files
KEYS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys')
shutil.rmtree(KEYS_FOLDER, ignore_errors=True)
os.mkdir(KEYS_FOLDER)

# data files
DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
shutil.rmtree(DATA_FOLDER, ignore_errors=True)
os.mkdir(DATA_FOLDER)

DB_FILE = os.path.join(DATA_FOLDER, 'vehicle_sensors.db')
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
SHARED_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared')
shutil.rmtree(SHARED_FOLDER, ignore_errors=True)
os.mkdir(SHARED_FOLDER)

# policy information
POLICY_INFO_FILE = os.path.join(SHARED_FOLDER, "policy_metadata.{}.json")

DATA_SOURCE_INFO_FILE = os.path.join(SHARED_FOLDER, 'data_source.msgpack')

# alicia-files
ALICIA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alicia-files')
shutil.rmtree(ALICIA_FOLDER, ignore_errors=True)
os.mkdir(ALICIA_FOLDER)

# bob-files
BOB_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bob-files')
shutil.rmtree(BOB_FOLDER, ignore_errors=True)
os.mkdir(BOB_FOLDER)

# We expect the url of the seednode to be local
port = os.getenv("TEST_VEHICLE_DATA_EXCHANGE_SEEDNODE_PORT")   # port used for unit test
if port is None:
    port = '11500'  # default local ursula
SEEDNODE_URL = f'localhost:{port}'


def cleanup():
    cleanup_directories = [KEYS_FOLDER, DATA_FOLDER, SHARED_FOLDER, BOB_FOLDER, ALICIA_FOLDER]
    for directory in cleanup_directories:
        shutil.rmtree(directory, ignore_errors=True)
