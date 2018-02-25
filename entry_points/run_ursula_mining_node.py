# This is not an actual mining script.  Don't use this to mine - you won't
# perform any re-encryptions, and you won't get paid.
# It might be (but might not be) useful for determining whether you have
# the proper depedencies and configuration to run an actual mining node.

# WIP w/ hendrix@8227c4abcb37ee6d27528a13ec22d55ee106107f

from nkms.characters import Ursula

_URSULA = Ursula(dht_port=3501, dht_interface="localhost")
_URSULA.listen()

from hendrix.deploy.base import HendrixDeploy

deployer = HendrixDeploy("start", {"wsgi":_URSULA.rest_app, "http_port": 3500})
deployer.reactor.callWhenRunning(_URSULA.start_datastore_in_threadpool)
deployer.run()
