import dash
import os

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash("NuCypher Heartbeat Data Sharing Application", external_stylesheets=external_stylesheets)
server = app.server
app.config.suppress_callback_exceptions = True

# ensure data folder exists
os.makedirs("./data", exist_ok=True)

DB_FILE = './data/heartbeats.db'
