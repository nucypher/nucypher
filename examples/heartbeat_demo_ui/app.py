import dash
import os
import shutil
from examples.heartbeat_demo_ui.demo_keys import KEYS_FOLDER

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Heartbeat Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True
app.title = "NuCypher Heartbeat Demo"

# remove old key files and re-create folder
shutil.rmtree(KEYS_FOLDER, ignore_errors=True)
os.mkdir(KEYS_FOLDER)

# remove old data files and re-create data folder
DATA_FOLDER = f'{os.path.dirname(os.path.abspath(__file__))}/data'
shutil.rmtree(DATA_FOLDER, ignore_errors=True)
os.mkdir(DATA_FOLDER)

DB_FILE = f'{DATA_FOLDER}/heartbeats.db'
DB_NAME = 'HeartBeat'

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
SEEDNODE_URL = "localhost:11500"
