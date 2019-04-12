Heartbeat Demo
====================

.. figure:: https://user-images.githubusercontent.com/2564234/49080419-dda35680-f243-11e8-90d7-6f649d80e03d.png
    :width: 100%

Overview
--------

.. important::

    This demo requires connecting to a running network. By default the demo is hardcoded to connect to the :doc:`local demo fleet </demos/local_fleet_demo>`.


Alicia has a Heart Monitor device that measures her heart rate and outputs this data in encrypted form.
Since Alicia knows that she may want to share this data in the future, she uses NuCypher to create
a *policy public key* for her Heart Monitor to use, so she can read and delegate access to the encrypted
data as she sees fit.

The Heart Monitor uses this public key to produce a file with some amount of encrypted heart rate measurements. 
This file is uploaded to a storage layer (e.g., IPFS, S3, or whatever you choose).

At some future point, she wants to share this information with other people, such as her Doctor.
Once she obtains her Doctor's public keys, she can create a policy in the NuCypher network granting access to him.
After this, her Doctor can read the file with encrypted data (which was uploaded by the Heart Monitor) and
request a re-encrypted ciphertext for each measurement, which can be opened with the Doctor's private key.

This simple example showcases many interesting and distinctive aspects of NuCypher:

- Alicia can create policy public keys **before knowing** the potential consumers.
- Alicia, or anyone knowing the policy public key (e.g., the Heart Monitor),
  can produce encrypted data that belongs to the policy.
  Again, this can happen **before granting access** to any consumer.
- As a consequence of the previous point, the Heart Monitor is completely
  unaware of the recipients. In its mind, it's producing data **for Alicia**.
- Alicia never interacts with the Doctor: she only needs the Doctor's public keys.
- Alicia only interacts with the NuCypher network for granting access to the Doctor.
  After this, she can even disappear from the face of the Earth.
- The Doctor never interacts with Alicia or the Heart Monitor:
  he only needs the encrypted data and some policy metadata.


The NuCypher Characters
-----------------------

The actors in this example can be mapped naturally to :doc:`Characters </api/characters>` in the NuCypher narrative:

- Since Alicia is the only one capable of granting access,
  she retains full control over the data encrypted for her.
  As such, she can be considered as the **data owner** or the **policy authority**.
  This corresponds to the :class:`~nucypher.characters.lawful.Alice` character.
- The Heart Monitor, or any other data sources that **encrypt data** on Alicia's behalf,
  is portrayed by the :class:`~nucypher.characters.lawful.Enrico` character.
- Nodes in the NuCypher network are called :class:`~nucypher.characters.lawful.Ursula` in our terminology.
  They receive the access policy from Alice and stand ready to
  re-encrypt data in exchange for payment in fees and token rewards.
  In a way, they **enforce the access policy** created by Alicia.
- The Doctor acts as a **data recipient**, and only can decrypt Alicia's data
  if she grants access to him. 
  This is modelled by the :class:`~nucypher.characters.lawful.Bob` character.

Install Nucypher
-----------------

Acquire the ``nucypher`` application code and install the dependencies.
For a full installation guide see the :doc:`/guides/installation_guide`.

Run the Demo
------------

Assuming you already have ``nucypher`` installed with the ``demos`` extra
and a :doc:`local fleet of Ursulas </demos/local_fleet_demo>` alive,
running the Heartbeat demo only involves executing the
``alicia.py`` and ``doctor.py`` scripts, contained in the
``examples/heartbeat_demo/cli`` directory.

First, run ``alicia.py``:

.. code::

    (nucypher)$ python alicia.py


This will create a temporal directory called ``alicia-files``
that contains the data for making Alicia persistent (i.e., her private keys).
Apart from that, it will also generate data and keys for the demo.
What's left is running the ``doctor.py`` script:

.. code::

    (nucypher)$ python doctor.py


This script will read the data generated in the previous step and retrieve
re-encrypted ciphertexts by means of the NuCypher network.
The result is printed in the console:

.. code::

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

