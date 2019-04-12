import dash
import os
import shutil

app = dash.Dash("NuCypher REST Heartbeat Data Sharing Application",
                assets_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets'),
                suppress_callback_exceptions=True)
server = app.server
app.title = "NuCypher REST Heartbeat Demo"

# remove old data files and re-create data folder
DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
shutil.rmtree(DATA_FOLDER, ignore_errors=True)
os.mkdir(DATA_FOLDER)

DB_FILE = os.path.join(DATA_FOLDER, 'heartbeats.db')
DB_NAME = 'HeartBeat'

# create shared folder for data shared between characters
SHARED_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared')
shutil.rmtree(SHARED_FOLDER, ignore_errors=True)
os.mkdir(SHARED_FOLDER)

# policy information
POLICY_INFO_FILE = os.path.join(SHARED_FOLDER, 'policy_metadata.{}.json')


def cleanup():
    cleanup_directories = [DATA_FOLDER, SHARED_FOLDER]
    for directory in cleanup_directories:
        shutil.rmtree(directory, ignore_errors=True)
