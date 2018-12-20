# NuCypher Streaming Heartbeat Demo

## How to run the demo

You will require two shells to execute the demo: one for generating heartbeats, the other for reading them

In shell 1, execute the following to generate simulated heartbeats:
```sh
$ pipenv shell

(nucypher)$ python generate-heartbeats.py
```

In shell 2, execute the following to graph the heartbeats
```sh
$ pipenv shell

(nucypher)$ python app.py
```
* The live heartbeat graph can be viewed at [http://127.0.0.1:8050/](http://127.0.0.1:8050/)
