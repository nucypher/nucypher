# NuCypher's Heartbeat Demo

![Heartbeat Demo](https://user-images.githubusercontent.com/2564234/49080419-dda35680-f243-11e8-90d7-6f649d80e03d.png)

Alicia has a Heart Monitor device that measures her heart rate and outputs this data in encrypted form.
Since she thinks that she may want to share this data in the future,
she uses NuCypher to create a _policy public key_ for the Heart Monitor to use,
so she can read and delegate access to the encrypted data as she sees fit.
The Heart Monitor uses this public key to produce a file with some amount of encrypted heart rate measurements;
this file is uploaded to some storage service (e.g., IPFS, S3, whatever). 

At some moment, she wants to share this information with other people, such as her Doctor.
Once she obtains her Doctor's public keys, she can create a policy in the NuCypher network granting access to him.
After this, her Doctor can read the file with encrypted data (which was uploaded by the Heart Monitor)
and request a re-encrypted ciphertext for each measurement, which can be opened with the Doctor's private key.

This simple use case showcases many interesting and distinctive aspects of NuCypher:
  - Alicia can create policy public keys **before knowing** who will be the potential consumers.
  - Alicia, or anyone knowing the policy public key (e.g., the Heart Monitor),
  can produce encrypted data that belongs to the policy. Again, this can happen before granting access to any consumer.
  - As a consequence of the previous point, Data Sources, like the Heart Monitor,
  are completely unaware of the recipients. In their mind, they are producing data **for Alicia**.
  - Alicia never interacts with the Doctor: she only needs the Doctor's public key.
  - Alicia only interacts with the NuCypher network for granting access to the Doctor.
  After this, she can even disappear from the face of the Earth.
  - The Doctor never interacts with Alicia or the Heart Monitor:
  he only needs the encrypted data and some policy metadata.

### How to run the demo 
Ensure that you already have `nucypher` installed.

Run a fleet of federated Ursulas in a separate terminal:

```sh
(nucypher)$ python ../run_demo_ursula_fleet.py
```
This will create a local network of federated Ursulas that will be used by the demo for re-encryption of data.

Subsequently, running the demo only involves running the `alicia.py` and `doctor.py` scripts.
You should run `alicia.py` first:

```sh
(nucypher)$ python alicia.py
```
This will create a temporal directory called `alicia-files` that contains the data for making Alicia persistent
(i.e., her private keys). Apart from that, it will also generate data and keys for the demo.
What's left is running the `doctor.py` script:

```sh
(nucypher)$ python doctor.py
```
This script will read the data generated in the previous step and retrieve re-encrypted ciphertexts via the NuCypher
network. The result is printed in the console:

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
