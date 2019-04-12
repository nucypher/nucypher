## Overview
A command line implementation of the Heartbeat Demo that uses 
the [NuCypher Python API](http://docs.nucypher.com/en/latest/api/characters.html).


### Run the Demo
Assuming you already have `nucypher` installed and a local demo fleet of Ursulas deployed, running the demo only involves running the `alicia.py` and `doctor.py` scripts. You should run `alicia.py` first:

```sh
(nucypher)$ python examples/heartbeat_demo/cli/alicia.py
```
This will create a temporal directory called `alicia-files` that contains the data for making Alicia persistent (i.e., her private keys). Apart from that, it will also generate data and keys for the demo. What's left is running the `doctor.py` script:

```sh
(nucypher)$ python examples/heartbeat_demo/cli/doctor.py
```
This script will read the data generated in the previous step and retrieve re-encrypted ciphertexts by means of the NuCypher network. The result is printed in the console:

```
Creating the Doctor ...
Doctor =  ⇀Maroon Snowman DarkSlateGray Bishop↽ (0xA36bcd5c5Cfa0C1119ea5E53621720a0C1a610F5)
The Doctor joins policy for label 'heart-data-❤️-e917d959'
----------------------❤︎ (82 BPM)                    Retrieval time:  3537.06 ms
---------------------❤︎ (81 BPM)                     Retrieval time:  2654.51 ms
-------------------------❤︎ (85 BPM)                 Retrieval time:  1513.32 ms
----------------------------❤︎ (88 BPM)              Retrieval time:  1552.66 ms
-----------------------❤︎ (83 BPM)                   Retrieval time:  1720.66 ms
---------------------❤︎ (81 BPM)                     Retrieval time:  1485.25 ms
---------------------❤︎ (81 BPM)                     Retrieval time:  1459.16 ms
---------------------❤︎ (81 BPM)                     Retrieval time:  1520.30 ms
----------------❤︎ (76 BPM)                          Retrieval time:  1479.54 ms
----------------❤︎ (76 BPM)                          Retrieval time:  1464.17 ms
---------------------❤︎ (81 BPM)                     Retrieval time:  1483.04 ms
----------------❤︎ (76 BPM)                          Retrieval time:  1687.72 ms
---------------❤︎ (75 BPM)                           Retrieval time:  1563.65 ms
```
