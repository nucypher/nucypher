import pandas as pd
import time
import random
import sqlite3
import os

db_dir = "./data/"
heartbeats_db_file = "heartbeats.db"
db_path = db_dir + heartbeats_db_file

# ensure data folder exists
os.makedirs(db_dir, exist_ok=True)

# remove any old heartbeat data
if os.path.exists(db_path):
    os.remove(db_path)

# generate new heartbeat data
db_conn = sqlite3.connect(db_path)

heart_rate = 80

while True:
    heart_rate = random.randint(max(60, heart_rate - 5),
                                min(100, heart_rate + 5))
    df = pd.DataFrame.from_dict({
                                 'Timestamp': [time.time()],
                                 'HR': [heart_rate]
                                })
    df.to_sql(name='HeartRates', con=db_conn, index=False, if_exists='append')
    print("Added heart rate measurement to db:", heart_rate)

    # generate per second heartbeats
    time.sleep(1)
