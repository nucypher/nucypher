## Overview
A UI application that implements the Heartbeat Demo and 
uses the [NuCypher Python API](http://docs.nucypher.com/en/latest/api/characters.html).


### Run the Demo
Assuming you already have `nucypher` installed and a local demo fleet of Ursulas deployed.

(After previously running `pipenv shell`)
```sh
(nucypher)$ python examples/heartbeat_demo/ui/streaming_heartbeat.py
```

* You can interact with the demo at [http://127.0.0.1:8050/](http://127.0.0.1:8050/)
    * Multiple `Bobs` can be created by repeatedly opening the Bob link in a new tab.
