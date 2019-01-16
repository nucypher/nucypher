import dash
import os
import shutil
from demo_keys import KEYS_FOLDER

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Heartbeat Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True

# remove old key files and re-create folder
shutil.rmtree(KEYS_FOLDER, ignore_errors=True)
os.mkdir(KEYS_FOLDER)

# remove old data files and re-create data folder
shutil.rmtree('./data', ignore_errors=True)
os.mkdir('./data')

DB_FILE = './data/heartbeats.db'
DB_NAME = 'HeartBeat'

# create shared folder for data shared between characters
SHARED_FOLDER = './shared'
shutil.rmtree(SHARED_FOLDER, ignore_errors=True)
os.mkdir(SHARED_FOLDER)
