.. _porter:

Porter Service
==============

Overview
--------
NuCypher Porter can be described as the *“Infura for NuCypher”*. Porter is a web-based service that performs
nucypher-based protocol operations on behalf of applications.

Its goal is to simplify and abstract the complexities surrounding the nucypher protocol to negate the need for
applications to interact with it via a python client. Porter introduces the nucypher protocol to cross-platform
functionality including web and mobile applications. By leveraging ``rust-umbral`` and its associated javascript
bindings for cryptography, and Porter for communication with the network, a lightweight, richer and full-featured
web and mobile experience is accessible to application developers.

.. image:: ../.static/img/porter_diagram.svg
    :target: ../.static/img/porter_diagram.svg


Running Porter
--------------
.. note::

    By default the Porter service will run on port 9155, unless specified otherwise.


via CLI
^^^^^^^
Install ``nucypher`` - see :doc:`/references/pip-installation`.

Usage
+++++
.. code:: console

    $ nucypher porter --help

    Usage: nucypher porter [OPTIONS] COMMAND [ARGS]...

      Porter management commands. Porter is a web-service that is the conduit
      between applications and the nucypher network, that performs actions on
      behalf of Alice and Bob.

    Options:
      --help  Show this message and exit.

    Commands:
      run                   Start Porter's Web controller.


.. code:: console

    $ nucypher porter run --help

    Usage: nucypher porter run [OPTIONS]

      Start Porter's Web controller.

    Options:
      -D, --debug                     Enable debugging mode, crashing on more
                                      exceptions instead of trying to recover.
                                      Also sets log level to "debug", turns on
                                      console and file logging and turns off
                                      Sentry logging.

      --log-level [critical|error|warn|info|debug]
                                      The log level for this process.  Is
                                      overridden by --debug.

      --sentry-logs / --no-sentry-logs
                                      Enable/disable logging to Sentry. Defaults
                                      to NUCYPHER_SENTRY_LOGS, or to `--sentry-
                                      logs` if it is not set.

      --file-logs / --no-file-logs    Enable/disable logging to file. Defaults to
                                      NUCYPHER_FILE_LOGS, or to `--file-logs` if
                                      it is not set.

      --console-logs / --no-console-logs
                                      Enable/disable logging to console. Defaults
                                      to `--no-console-logs`.

      -J, --json-ipc                  Send all IPC output to stdout as JSON, and
                                      turn off the rest

      -L, --no-logs                   Disable all logging output
      -Q, --quiet                     Disable console messages
      -v, --verbose                   Verbose console messages
      --network NUCYPHER_NETWORK_NAME
                                      NuCypher Network/Domain Name
      --provider TEXT                 Blockchain provider's URI i.e.
                                      'file:///path/to/geth.ipc'

      -F, --federated-only / --decentralized
                                      Connect only to federated nodes
      --teacher TEXT                  An Ursula URI to start learning from
                                      (seednode)

      --registry-filepath FILE        Custom contract registry filepath
      --http-port INTEGER RANGE       Porter HTTP/HTTPS port for JSON endpoint
      --certificate-filepath FILE     Pre-signed TLS certificate filepath
      --tls-key-filepath FILE         TLS private key filepath
      -x, --dry-run                   Execute normally without actually starting
                                      Porter

      --eager                         Start learning and scraping the network
                                      before starting up other services

      --help                          Show this message and exit.


.. code:: console

    $ nucypher porter run --provider <YOUR WEB3 PROVIDER URI> --network mainnet


     ______
    (_____ \           _
     _____) )__   ____| |_  ____  ____
    |  ____/ _ \ / ___)  _)/ _  )/ ___)
    | |   | |_| | |   | |_( (/ /| |
    |_|    \___/|_|    \___)____)_|

    the Pipe for nucypher network operations

    Reading Latest Chaindata...
    Network: Mainnet
    Provider: ...
    Running Porter Web Controller at http://127.0.0.1:9155


To run via https use the ``--tls-key-filepath`` and ``--certificate-filepath`` options:

.. code:: console

    $ nucypher porter run --provider <YOUR WEB3 PROVIDER URI> --network mainnet --tls-key-filepath <TLS KEY FILEPATH> --certificate-filepath <CERT FILEPATH>


     ______
    (_____ \           _
     _____) )__   ____| |_  ____  ____
    |  ____/ _ \ / ___)  _)/ _  )/ ___)
    | |   | |_| | |   | |_( (/ /| |
    |_|    \___/|_|    \___)____)_|

    the Pipe for nucypher network operations

    Reading Latest Chaindata...
    Network: Mainnet
    Provider: ...
    Running Porter Web Controller at https://127.0.0.1:9155


via Docker
^^^^^^^^^^
TBD


API
---

Status Codes
^^^^^^^^^^^^
All documented API endpoints use JSON and are REST-like.

Some common returned status codes you may encounter are:

- ``200 OK`` -- The request has succeeded.
- ``400 BAD REQUEST`` -- The server cannot or will not process the request due to something that is perceived to
  be a client error (e.g., malformed request syntax, invalid request message framing, or deceptive request routing).
- ``500 INTERNAL SERVER ERROR`` -- The server encountered an unexpected condition that prevented it from
  fulfilling the request.

Typically, you will want to ensure that any given response results in a 200 status code.
This indicates that the server successfully completed the call.

If a 400 status code is returned, double-check the request data being sent to the server. The text provided in the
error response should describe the nature of the problem.

If a 500 status code, note the reason provided. If the error is ambiguous or unexpected, we'd like to
know about it! The text provided in the error response should describe the nature of the problem.

For any bugs/un expected errors, see our :ref:`Contribution Guide <contribution-guide>` for issue reporting and
getting involved. Please include contextual information about the sequence of steps that caused the 500 error in the
GitHub issue. For any questions, message us in our `Discord <https://discord.gg/7rmXa3S>`_.


GET /get_ursulas
^^^^^^^^^^^^^^^^
Sample available Ursulas for a policy as part of Alice's ``grant`` workflow. Returns a list of Ursulas
and their associated information that is used for the policy.

Parameters
++++++++++
+----------------------------------+---------------+-----------------------------------------------+
| **Parameter**                    | **Type**      | **Description**                               |
+==================================+===============+===============================================+
| ``quantity``                     | Integer       | Number of total Ursulas to return.            |
+----------------------------------+---------------+-----------------------------------------------+
| ``duration_periods``             | Integer       | Number of periods required for the policy.    |
+----------------------------------+---------------+-----------------------------------------------+
| ``include_ursulas`` *(Optional)* | List[Strings] | | List of Ursula checksum addresses to        |
|                                  |               | | give preference to. If any of these Ursulas |
|                                  |               | | are unavailable, they will not be included  |
|                                  |               | | in result.                                  |
+----------------------------------+---------------+-----------------------------------------------+
| ``exclude_ursulas`` *(Optional)* | List[Strings] | | List of Ursula checksum addresses to not    |
|                                  |               | | include in the result.                      |
+----------------------------------+---------------+-----------------------------------------------+

Returns
+++++++
List of Ursulas with associated information:

    * ``encrypting_key`` - Ursula's encrypting key encoded as hex
    * ``checksum_address`` - Ursula's checksum address
    * ``uri`` - Ursula's URI

Example Request
+++++++++++++++
.. code:: bash

    curl -X GET <PORTER_URI>/get_ursulas \
        -H "Content-Type: application/json" \
        -d '{"quantity": 5, "duration_periods": 4}'

Example Response
++++++++++++++++
.. code::

    Status: 200 OK


.. code:: json

    {
       "result": {
          "ursulas": [
             {
                "encrypting_key": "025a335eca37edce8191d43c156e7bc6b451b21e5258759966bbfe0e6ce44543cb",
                "checksum_address": "0x5cF1703A1c99A4b42Eb056535840e93118177232",
                "uri": "https://3.236.144.36:9151"
             },
             {
                "encrypting_key": "02b0a0099ee180b531b4937bd7446972296447b2479ca6259cb6357ed98b90da3a",
                "checksum_address": "0x7fff551249D223f723557a96a0e1a469C79cC934",
                "uri": "https://54.218.83.166:9151"
             },
             {
                "encrypting_key": "02761c765e2f101df39a5f680f3943d0d993ef9576de8a3e0e5fbc040d6f8c15a5",
                "checksum_address": "0x9C7C824239D3159327024459Ad69bB215859Bd25",
                "uri": "https://92.53.84.156:9151"
             },
             {
                "encrypting_key": "0258b7c79fe73f3499de91dd5a5341387184035d0555b10e6ac762d211a39684c0",
                "checksum_address": "0x9919C9f5CbBAA42CB3bEA153E14E16F85fEA5b5D",
                "uri": "https://3.36.66.164:9151"
             },
             {
                "encrypting_key": "02e43a623c24db4f62565f82b6081044c1968277edfdca494a81c8fd0826e0adf6",
                "checksum_address": "0xfBeb3368735B3F0A65d1F1E02bf1d188bb5F5BE6",
                "uri": "https://128.199.124.254:9151"
             }
          ]
       },
       "version": "5.2.0"
    }


POST /publish_treasure_map
^^^^^^^^^^^^^^^^^^^^^^^^^^
Publish a treasure map to the network as part of Alice's ``grant`` workflow. The treasure map associated
with the policy is stored by the network.

Parameters
++++++++++
+----------------------------------+---------------+----------------------------------------+
| **Parameter**                    | **Type**      | **Description**                        |
+==================================+===============+========================================+
| ``treasure_map``                 | String        | Treasure map bytes encoded as base64.  |
+----------------------------------+---------------+----------------------------------------+
| ``bob_encrypting_key``           | String        | Bob's encrypting key encoded as hex.   |
+----------------------------------+---------------+----------------------------------------+

Returns
+++++++
No data - only the status code is relevant.

Example Request
+++++++++++++++
.. code:: bash

    curl -X POST <PORTER_URI>/publish_treasure_map \
        -H "Content-Type: application/json" \
        -d '{"treasure_map": "Qld7S8sbKFCv2B8KxfJo4oxiTOjZ4VPyqTK5K1xK6DND6TbLg2hvlGaMV69aiiC5QfadB82w/5q1Sw+SNFHN2esWgAbs38QuUVUGCzDoWzQAAAGIAuhw12ZiPMNV8LaeWV8uUN+au2HGOjWilqtKsaP9fmnLAzFiTUAu9/VCxOLOQE88BPoWk1H7OxRLDEhnBVYyflpifKbOYItwLLTtWYVFRY90LtNSAzS8d3vNH4c3SHSZwYsCKY+5LvJ68GD0CqhydSxCcGckh0unttHrYGSOQsURUI4AAAEBsSMlukjA1WyYA+FouqkuRtk8bVHcYLqRUkK2n6dShEUGMuY1SzcAbBINvJYmQp+hhzK5m47AzCl463emXepYZQC/evytktG7yXxd3k8Ak+Qr7T4+G2VgJl4YrafTpIT6wowd+8u/SMSrrf/M41OhtLeBC4uDKjO3rYBQfVLTpEAgiX/9jxB80RtNMeCwgcieviAR5tlw2IlxVTEhxXbFeopcOZmfEuhVWqgBUfIakqsNCXkkubV0XS2l5G1vtTM8oNML0rP8PyKd4+0M5N6P/EQqFkHH93LCDD0IQBq9usm3MoJp0eT8N3m5gprI05drDh2xe/W6qnQfw3YXnjdvf2A=", \
             "bob_encrypting_key": "026d1f4ce5b2474e0dae499d6737a8d987ed3c9ab1a55e00f57ad2d8e81fe9e9ac"}'

Example Response
++++++++++++++++
.. code::

    Status: 200 OK


.. code:: json

    {
       "result": {},
       "version": "5.2.0"
    }


GET /get_treasure_map
^^^^^^^^^^^^^^^^^^^^^
Retrieve a treasure map from the network as part of Bob's ``retrieve`` workflow. Bob needs to obtain the treasure map
associated with a policy, to learn which Ursulas were assigned to service the policy.

Parameters
++++++++++
+----------------------------------+---------------+----------------------------------------+
| **Parameter**                    | **Type**      | **Description**                        |
+==================================+===============+========================================+
| ``treasure_map_id``              | String        | Treasure map identifier.               |
+----------------------------------+---------------+----------------------------------------+
| ``bob_encrypting_key``           | String        | Bob's encrypting key encoded as hex.   |
+----------------------------------+---------------+----------------------------------------+


Returns
+++++++
The requested treasure map:

    * ``treasure_map``: Treasure map bytes encoded as base64

Example Request
+++++++++++++++
.. code:: bash

    curl -X GET <PORTER_URI>/get_treasure_map \
        -H "Content-Type: application/json" \
        -d '{"treasure_map_id": "f6ec73c93084ce91d5542a4ba6070071f5565112fe19b26ae9c960f9d658903a", \
             "bob_encrypting_key": "026d1f4ce5b2474e0dae499d6737a8d987ed3c9ab1a55e00f57ad2d8e81fe9e9ac"}'

Example Response
++++++++++++++++
.. code::

    Status: 200 OK


.. code:: json

    {
       "result": {
          "treasure_map": "Qld7S8sbKFCv2B8KxfJo4oxiTOjZ4VPyqTK5K1xK6DND6TbLg2hvlGaMV69aiiC5QfadB82w/5q1Sw+SNFHN2esWgAbs38QuUVUGCzDoWzQAAAGIAuhw12ZiPMNV8LaeWV8uUN+au2HGOjWilqtKsaP9fmnLAzFiTUAu9/VCxOLOQE88BPoWk1H7OxRLDEhnBVYyflpifKbOYItwLLTtWYVFRY90LtNSAzS8d3vNH4c3SHSZwYsCKY+5LvJ68GD0CqhydSxCcGckh0unttHrYGSOQsURUI4AAAEBsSMlukjA1WyYA+FouqkuRtk8bVHcYLqRUkK2n6dShEUGMuY1SzcAbBINvJYmQp+hhzK5m47AzCl463emXepYZQC/evytktG7yXxd3k8Ak+Qr7T4+G2VgJl4YrafTpIT6wowd+8u/SMSrrf/M41OhtLeBC4uDKjO3rYBQfVLTpEAgiX/9jxB80RtNMeCwgcieviAR5tlw2IlxVTEhxXbFeopcOZmfEuhVWqgBUfIakqsNCXkkubV0XS2l5G1vtTM8oNML0rP8PyKd4+0M5N6P/EQqFkHH93LCDD0IQBq9usm3MoJp0eT8N3m5gprI05drDh2xe/W6qnQfw3YXnjdvf2A="
       },
       "version": "5.2.0"
    }
