# This is not an actual mining script.  Don't use this to mine - you won't
# perform any re-encryptions, and you won't get paid.
# It might be (but might not be) useful for determining whether you have
# the proper depedencies and configuration to run an actual mining node.

# WIP w/ hendrix@83519da900a258d8e27a3b1fedee949414d2de26

import os
from nkms.characters import Ursula
DB_NAME = "non-mining-proxy-node"

_URSULA = Ursula(dht_port=3501, dht_interface="localhost", db_name=DB_NAME)
_URSULA.listen()

from hendrix.deploy.base import HendrixDeploy

deployer = HendrixDeploy("start", {"wsgi":_URSULA.rest_app, "http_port": 3500})

try:
    deployer.run()
finally:
    os.remove(DB_NAME)
