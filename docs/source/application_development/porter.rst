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

To run the Porter service over HTTPS, it will require a TLS key and a certificate. If desired, self-signed certificates
can be created for the localhost using the ``openssl`` command:

.. code:: bash

    $ openssl req -x509 -out cert.pem -keyout key.pem \
      -newkey rsa:2048 -nodes -sha256 \
      -subj '/CN=localhost' -extensions EXT -config <( \
        printf "[dn]\nCN=localhost\n[req]\ndistinguished_name = dn\n[EXT]\nsubjectAltName=DNS:localhost\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth")

via Docker
^^^^^^^^^^

Run Porter within Docker without acquiring or installing the ``nucypher`` codebase.

#. Get the latest ``nucypher`` image:

   .. code:: bash

       docker pull nucypher/nucypher:latest

#. Run Porter service

   For HTTP service (on default port 80):

   .. code:: bash

       $ docker run -d --rm \
          --name porter-http \
          -v ~/.local/share/nucypher/:/root/.local/share/nucypher \
          -p 80:9155 \
          nucypher/nucypher:latest \
          nucypher porter run \
          --provider <YOUR WEB3 PROVIDER URI> \
          --network <NETWORK NAME>

   For HTTPS service (on default port 443):

   .. code:: bash

       $ docker run -d --rm \
          --name porter-https \
          -v ~/.local/share/nucypher/:/root/.local/share/nucypher \
          -v <TLS DIRECTORY>:/etc/porter-tls
          -p 443:9155 \
          nucypher/nucypher:latest \
          nucypher porter run \
          --provider <YOUR WEB3 PROVIDER URI> \
          --network <NETWORK NAME> \
          --tls-key-filepath /etc/porter-tls/<KEY FILENAME> \
          --tls-certificate-filepath /etc/porter-tls/<CERT FILENAME>

   The ``<TLS DIRECTORY>`` is expected to contain the TLS key file (``<KEY FILENAME>``) and the certificate (``<CERT FILENAME>``) to run Porter over HTTPS.

#. Porter will be available on default ports 80 (HTTP) or 443 (HTTPS).

#. View Porter logs

   .. code:: bash

       $ docker logs -f porter-http

   or

   .. code:: bash

       $ docker logs -f porter-https

#. Stop Porter service

   .. code:: bash

       $ docker stop porter-http

   or

   .. code:: bash

       $ docker stop porter-https


via Docker Compose
^^^^^^^^^^^^^^^^^^

Docker Compose will start the Porter service within a Docker container.

#. Acquire the ``nucypher`` codebase - see :ref:`acquire_codebase`. Note that there is no need
   to install ``nucypher`` after acquiring the codebase.

#. Set the required environment variables:

   * Web3 Provider URI environment variable

     .. code:: bash

         $ export WEB3_PROVIDER_URI=<YOUR WEB3 PROVIDER URI>

     .. note::

         Local ipc is not supported when running via Docker.


   * Network Name environment variable

     .. code:: bash

         $ export NUCYPHER_NETWORK=<NETWORK NAME>

   * (Optional) TLS directory variable containing the TLS key and the certificate to run Porter over HTTPS. The directory is expected to contain two files:

        * ``key.pem`` - the TLS key
        * ``cert.pem`` - the TLS certificate

     Set the TLS directory environment variable

     .. code:: bash

         export TLS_DIR=<ABSOLUTE PATH TO TLS DIRECTORY>

#. Run Porter service

   For HTTP service (on default port 80):

   .. code:: bash

       $ docker-compose -f deploy/docker/porter/docker-compose.yml up -d porter-http

   For HTTPS service (on default port 443):

   .. code:: bash

       $ docker-compose -f deploy/docker/porter/docker-compose.yml up -d porter-https

#. Porter will be available on default ports 80 (HTTP) or 443 (HTTPS).

#. View Porter logs

   .. code:: bash

       $ docker-compose -f deploy/docker/porter/docker-compose.yml logs -f <SERVICE_NAME>

#. Stop Porter service

   .. code:: bash

       $ docker-compose -f deploy/docker/porter/docker-compose.yml down


via CLI
^^^^^^^

Install ``nucypher`` - see :doc:`/references/pip-installation`.

For a full list of CLI options, run:

  .. code:: console

      $ nucypher porter run --help


* Run Porter service
  * Run via HTTP

  .. code:: console

      $ nucypher porter run --provider <YOUR WEB3 PROVIDER URI> --network <NETWORK NAME>


       ______
      (_____ \           _
       _____) )__   ____| |_  ____  ____
      |  ____/ _ \ / ___)  _)/ _  )/ ___)
      | |   | |_| | |   | |_( (/ /| |
      |_|    \___/|_|    \___)____)_|

      the Pipe for nucypher network operations

      Reading Latest Chaindata...
      Network: <NETWORK NAME>
      Provider: ...
      Running Porter Web Controller at http://127.0.0.1:9155

  * Run via HTTPS

  To run via HTTPS use the ``--tls-key-filepath`` and ``--tls-certificate-filepath`` options:

  .. code:: console

      $ nucypher porter run --provider <YOUR WEB3 PROVIDER URI> --network <NETWORK NAME> --tls-key-filepath <TLS KEY FILEPATH> --tls-certificate-filepath <CERT FILEPATH>


       ______
      (_____ \           _
       _____) )__   ____| |_  ____  ____
      |  ____/ _ \ / ___)  _)/ _  )/ ___)
      | |   | |_| | |   | |_( (/ /| |
      |_|    \___/|_|    \___)____)_|

      the Pipe for nucypher network operations

      Reading Latest Chaindata...
      Network: <NETWORK NAME>
      Provider: ...
      Running Porter Web Controller at https://127.0.0.1:9155


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
Confirmation that the treasure map was published:

    * ``published`` - Value of ``true``.

If publishing the treasure map fails, an error status code is returned.

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
       "result": {
          "published": true
       },
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

    * ``treasure_map`` - Treasure map bytes encoded as base64

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
