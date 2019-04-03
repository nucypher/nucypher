import dash
import os
import shutil

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Heartbeat Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True
app.title = "NuCypher Heartbeat Demo"

# remove old data files and re-create data folder
DATA_FOLDER = f'{os.path.dirname(os.path.abspath(__file__))}/data'
shutil.rmtree(DATA_FOLDER, ignore_errors=True)
os.mkdir(DATA_FOLDER)

DB_FILE = os.path.join(DATA_FOLDER, 'heartbeats.db')
DB_NAME = 'HeartBeat'

# create shared folder for data shared between characters
SHARED_FOLDER = f'{os.path.dirname(os.path.abspath(__file__))}/shared'
shutil.rmtree(SHARED_FOLDER, ignore_errors=True)
os.mkdir(SHARED_FOLDER)

# policy information
POLICY_INFO_FILE = os.path.join(SHARED_FOLDER, 'policy_metadata.{}.json')
