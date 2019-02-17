import dash
import os
import shutil

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Heartbeat Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True
app.title = "NuCypher Heartbeat Demo"

# remove old data files and re-create data folder
shutil.rmtree('./data', ignore_errors=True)
os.mkdir('./data')

# create shared folder for data shared between characters
SHARED_FOLDER = './shared'
shutil.rmtree(SHARED_FOLDER, ignore_errors=True)
os.mkdir(SHARED_FOLDER)

DB_FILE = './data/heartbeats.db'
DB_NAME = 'HeartBeat'
