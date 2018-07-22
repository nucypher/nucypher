# This is not an actual mining script.  Don't use this to mine - you won't
# perform any re-encryptions, and you won't get paid.
# It might be (but might not be) useful for determining whether you have
# the proper depedencies and configuration to run an actual mining node.

# WIP w/ hendrix@tags/3.3.0rc1

import os, sys

import asyncio
from contextlib import suppress

from nucypher.characters import Ursula


DB_NAME = "examples-runtime-cruft/db"
STARTING_PORT = 3501


import logging, binascii
import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)


def spin_up_ursula(dht_port, rest_port, db_name, teachers=()):
    metadata_file = "examples-runtime-cruft/node-metadata-{}".format(rest_port)

    asyncio.set_event_loop(asyncio.new_event_loop())  # Ugh.  Awful.  But needed until we shed the DHT.
    _URSULA = Ursula(dht_port=dht_port,
                     rest_port=rest_port,
                     rest_host="localhost",
                     dht_host="localhost",
                     db_name=db_name,
                     federated_only=True,
                     known_nodes=teachers,
                     )
    _URSULA.dht_listen()
    try:
        with open(metadata_file, "w") as f:
            f.write(bytes(_URSULA).hex())
        _URSULA.start_learning_loop()
        _URSULA.get_deployer().run()
    finally:
        os.remove(db_name)
        os.remove(metadata_file)


if __name__ == "__main__":
    try:
        teacher_dht_port = sys.argv[2]
        teacher_rest_port = int(teacher_dht_port) + 100
        with open("examples-runtime-cruft/node-metadata-{}".format(teacher_rest_port), "r") as f:
            f.seek(0)
            teacher_bytes = binascii.unhexlify(f.read())
        teacher = Ursula.from_bytes(teacher_bytes, federated_only=True)
        teachers = (teacher, )
        print("Will learn from {}".format(teacher))
    except (IndexError, FileNotFoundError):
        teachers = ()

    dht_port = sys.argv[1]
    rest_port = int(dht_port) + 100
    db_name = DB_NAME + str(rest_port)
    spin_up_ursula(dht_port, rest_port, db_name, teachers=teachers)

