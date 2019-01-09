import dash
import os
import shutil

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Heartbeat Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True

# remove old data files and re-create data folder
shutil.rmtree('./data', ignore_errors=True)
os.mkdir("./data")

DB_FILE = './data/heartbeats.db'
