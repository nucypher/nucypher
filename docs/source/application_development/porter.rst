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

    If running the Porter service using Docker or Docker Compose, it will run on port 80 (HTTP) or 443 (HTTPS). If
    running via the CLI the default port is 9155, unless specified otherwise via the ``--http-port`` option.

Security
^^^^^^^^

HTTPS
+++++
To run the Porter service over HTTPS, it will require a TLS key (``--tls-key-filepath`` option) and a TLS certificate.

If desired, keys and self-signed certificates can be created for the localhost using the ``openssl`` command:

.. code:: bash

    $ openssl req -x509 -out cert.pem -keyout key.pem \
      -newkey rsa:2048 -nodes -sha256 \
      -subj '/CN=localhost' -extensions EXT -config <( \
        printf "[dn]\nCN=localhost\n[req]\ndistinguished_name = dn\n[EXT]\nsubjectAltName=DNS:localhost\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth")

.. important::

    Self-signed certificates are not recommended, other than for testing.


Authentication
++++++++++++++
Porter will allow the configuration of Basic Authentication out of the box via
an `htpasswd <https://httpd.apache.org/docs/2.4/programs/htpasswd.html>`_ file. The use of Basic Authentication
necessitates HTTPS since user credentials will be passed over the network as cleartext.

Alternative authentication mechanisms can be implemented outside of Porter via an intermediary proxy service, for
example an Nginx HTTPS reverse proxy.


via Docker
^^^^^^^^^^

Run Porter within Docker without acquiring or installing the ``nucypher`` codebase.

#. Get the latest ``nucypher`` image:

   .. code:: bash

       $ docker pull nucypher/porter:latest

#. Run Porter service

   For HTTP service (on default port 80):

   .. code:: bash

       $ docker run -d --rm \
          --name porter-http \
          -v ~/.local/share/nucypher/:/root/.local/share/nucypher \
          -p 80:9155 \
          nucypher/porter:latest \
          nucypher porter run \
          --provider <YOUR WEB3 PROVIDER URI> \
          --network <NETWORK NAME>

   For HTTPS service (on default port 443):

   * Without Basic Authentication:

     .. code:: bash

         $ docker run -d --rm \
            --name porter-https \
            -v ~/.local/share/nucypher/:/root/.local/share/nucypher \
            -v <TLS DIRECTORY>:/etc/porter/tls \
            -p 443:9155 \
            nucypher/porter:latest \
            nucypher porter run \
            --provider <YOUR WEB3 PROVIDER URI> \
            --network <NETWORK NAME> \
            --tls-key-filepath /etc/porter/tls/<KEY FILENAME> \
            --tls-certificate-filepath /etc/porter/tls/<CERT FILENAME>

   * With Basic Authentication:

     .. code:: bash

         $ docker run -d --rm \
            --name porter-https-auth \
            -v ~/.local/share/nucypher/:/root/.local/share/nucypher \
            -v <TLS DIRECTORY>:/etc/porter/tls \
            -v <HTPASSWD FILE>:/etc/porter/auth/htpasswd \
            -p 443:9155 \
            nucypher/porter:latest \
            nucypher porter run \
            --provider <YOUR WEB3 PROVIDER URI> \
            --network <NETWORK NAME> \
            --tls-key-filepath /etc/porter/tls/<KEY FILENAME> \
            --tls-certificate-filepath /etc/porter/tls/<CERT FILENAME> \
            --basic-auth-filepath /etc/porter/auth/htpasswd

   The ``<TLS DIRECTORY>`` is expected to contain the TLS key file (``<KEY FILENAME>``) and the
   certificate (``<CERT FILENAME>``) to run Porter over HTTPS.


#. Porter will be available on default ports 80 (HTTP) or 443 (HTTPS). The porter service running will be one of
   the following depending on the mode chosen:

   * ``porter-http``
   * ``porter-https``
   * ``porter-https-auth``

#. View Porter logs

   .. code:: bash

       $ docker logs -f <PORTER SERVICE>

#. Stop Porter service

   .. code:: bash

       $ docker stop <PORTER SERVICE>


via Docker Compose
^^^^^^^^^^^^^^^^^^

Docker Compose will start the Porter service within a Docker container.

#. Acquire the ``nucypher`` codebase - see :ref:`acquire_codebase`. There is no need
   to install ``nucypher`` after acquiring the codebase since Docker will be used.

#. Set the required environment variables:

   * Web3 Provider URI environment variable

     .. code:: bash

         $ export WEB3_PROVIDER_URI=<YOUR WEB3 PROVIDER URI>

     .. note::

         Local ipc is not supported when running via Docker.


   * Network Name environment variable

     .. code:: bash

         $ export NUCYPHER_NETWORK=<NETWORK NAME>

   * *(Optional)* TLS directory variable containing the TLS key and the certificate to run Porter over HTTPS. The directory is expected to contain two files:

     * ``key.pem`` - the TLS key
     * ``cert.pem`` - the TLS certificate

     Set the TLS directory environment variable

     .. code:: bash

         $ export TLS_DIR=<ABSOLUTE PATH TO TLS DIRECTORY>

   * *(Optional)* Filepath to the htpasswd file for Basic Authentication

     Set the htpasswd filepath environment variable

     .. code:: bash

         $ export HTPASSWD_FILE=<ABSOLUTE PATH TO HTPASSWD FILE>

#. Run Porter service

   For HTTP service (on default port 80):

   .. code:: bash

       $ docker-compose -f deploy/docker/porter/docker-compose.yml up -d porter-http

   For HTTPS service (on default port 443):

   * Without Basic Authentication

     .. code:: bash

         $ docker-compose -f deploy/docker/porter/docker-compose.yml up -d porter-https

   * With Basic Authentication

     .. code:: bash

         $ docker-compose -f deploy/docker/porter/docker-compose.yml up -d porter-https-auth

#. Porter will be available on default ports 80 (HTTP) or 443 (HTTPS). The porter service running will be one of
   the following depending on the mode chosen:

   * ``porter-http``
   * ``porter-https``
   * ``porter-https-auth``

#. View Porter logs

   .. code:: bash

       $ docker-compose -f deploy/docker/porter/docker-compose.yml logs -f <PORTER SERVICE>

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

    For HTTPS with Basic Authentication, add the ``--basic-auth-filepath`` option:

    .. code:: console

        $ nucypher porter run --provider <YOUR WEB3 PROVIDER URI> --network <NETWORK NAME> --tls-key-filepath <TLS KEY FILEPATH> --tls-certificate-filepath <CERT FILEPATH> --basic-auth-filepath <HTPASSWD FILE>


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
        Basic Authentication enabled
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
- ``401 UNAUTHORIZED`` -- Authentication is required and the request has failed to provide valid authentication credentials.
- ``500 INTERNAL SERVER ERROR`` -- The server encountered an unexpected condition that prevented it from
  fulfilling the request.

Typically, you will want to ensure that any given response results in a 200 status code.
This indicates that the server successfully completed the call.

If a 400 status code is returned, double-check the request data being sent to the server. The text provided in the
error response should describe the nature of the problem.

If a 401 status code is returned, ensure that valid authentication credentials are being used in the request e.g. if
Basic authentication is enabled.

If a 500 status code, note the reason provided. If the error is ambiguous or unexpected, we'd like to
know about it! The text provided in the error response should describe the nature of the problem.

For any bugs/un expected errors, see our :ref:`Contribution Guide <contribution-guide>` for issue reporting and
getting involved. Please include contextual information about the sequence of steps that caused the 500 error in the
GitHub issue. For any questions, message us in our `Discord <https://discord.gg/7rmXa3S>`_.


URL Query Parameters
^^^^^^^^^^^^^^^^^^^^
All parameters can be passed as either JSON data within the request or as query parameter strings in the URL.
Query parameters used within the URL will need to be URL encoded e.g. ``/`` in a base64 string becomes ``%2F`` etc.

For ``List`` data types to be passed via a URL query parameter, the value should be provided as a comma-delimited
String. For example, if a parameter is of type ``List[String]`` either a JSON list of strings can be provided e.g.

.. code:: bash

    curl -X GET <PORTER URI>/<ENDPOINT> \
        -H "Content-Type: application/json" \
        -d '{"parameter_with_list_of_values": ["value1", "value2", "value3"]}'

OR it can be provided via a URL query parameter

.. code:: bash

    curl -X GET <PORTER URI>/<ENDPOINT>?parameter_with_list_of_values=value1,value2,value3

More examples shown below.

.. important::

    If URL query parameters are used and the URL becomes too long, the request will fail. There is no official limit
    and it is dependent on the tool being used.


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
| ``include_ursulas`` *(Optional)* | List[String]  | | List of Ursula checksum addresses to        |
|                                  |               | | give preference to. If any of these Ursulas |
|                                  |               | | are unavailable, they will not be included  |
|                                  |               | | in result.                                  |
+----------------------------------+---------------+-----------------------------------------------+
| ``exclude_ursulas`` *(Optional)* | List[String]  | | List of Ursula checksum addresses to not    |
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

    curl -X GET <PORTER URI>/get_ursulas \
        -H "Content-Type: application/json" \
        -d '{"quantity": 5,
             "duration_periods": 4,
             "include_ursulas": ["0xB04FcDF9327f65AB0107Ea95b78BB200C07FA752"],
             "exclude_ursulas": ["0x5cF1703A1c99A4b42Eb056535840e93118177232", "0x9919C9f5CbBAA42CB3bEA153E14E16F85fEA5b5D"]}'

OR

.. code:: bash

    curl -X GET "<PORTER URI>/get_ursulas?quantity=5&duration_periods=4&include_ursulas=0xB04FcDF9327f65AB0107Ea95b78BB200C07FA752&exclude_ursulas=0x5cF1703A1c99A4b42Eb056535840e93118177232,0x9919C9f5CbBAA42CB3bEA153E14E16F85fEA5b5D"


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
       "version": "6.0.0"
    }


POST /retrieve_cfrags
^^^^^^^^^^^^^^^^^^^^^
Get data re-encrypted by the network as part of Bob's ``retrieve`` workflow.

Parameters
++++++++++
+-------------------------------------------+---------------+----------------------------------------+
| **Parameter**                             | **Type**      | **Description**                        |
+===========================================+===============+========================================+
| ``treasure_map``                          | String        | | Unencrypted treasure map bytes       |
|                                           |               | | encoded as base64.                   |
+-------------------------------------------+---------------+----------------------------------------+
| ``retrieval_kits``                        | List[String]  | | List of retrieval kits bytes encoded |
|                                           |               | | as base64.                           |
+-------------------------------------------+---------------+----------------------------------------+
| ``alice_verifying_key``                   | String        | Alice's verifying key encoded as hex.  |
+-------------------------------------------+---------------+----------------------------------------+
| ``bob_encrypting_key``                    | String        | Bob's encrypting key encoded as hex.   |
+-------------------------------------------+---------------+----------------------------------------+
| ``bob_verifying_key``                     | String        | Bob's verifying key encoded as hex.    |
+-------------------------------------------+---------------+----------------------------------------+
| ``policy_encrypting_key``                 | String        | | Encrypting key used for the policy   |
|                                           |               | | encoded as hex.                      |
+-------------------------------------------+---------------+----------------------------------------+
| ``publisher_verifying_key`` *(Optional)*  | String        | Treasure map publisher's verifying key |
|                                           |               | | encoded as hex.                      |
+-------------------------------------------+---------------+----------------------------------------+


Returns
+++++++
The result of the re-encryption operations performed:

    * ``retrieval_results`` - The list of retrieval results of the re-encryption operations containing capsules, and associated cfrags produced by different ursulas.

Example Request
+++++++++++++++
.. code:: bash

    curl -X POST <PORTER URI>/retrieve_cfrags \
        -H "Content-Type: application/json" \
        -d '{"treasure_map": "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",
             "retrieval_kits": ["gANDYgMKitDPd/QttLGy+s7Oacnm8pfbl3Qs2UD3IS1d9wF3awJsXnjFq7OkRQE45DV4+Ma2lDSJ5SeKEBqJK5GdPMB6CRwJ1hX7Y5SYgzpZtr/Z5/S3DHgVKn+8fWX92FaqEXIGcQBjYnVpbHRpbnMKc2V0CnEBXXEChXEDUnEEhnEFLg=="],
             "alice_verifying_key": "02d3389864e9e7206ae1d18301bbd67ad8e0bdf257b3085c9aa13e9438ff9133f2",
             "bob_encrypting_key": "03d41cb7aa2df98cb9fb1591b5556363862a367faae6d0e4874a860321141788cb",
             "bob_verifying_key": "039c19e5d44b016af126d89488c4ae5599e0fde9ea30047754d1fe173d05eee468",
             "policy_encrypting_key": "02cdb2cec70b568c0624b72450c2043836aa831b06b196a50db461e87acddb791e"}'

OR

.. code:: bash

    curl -X POST "<PORTER URI>/retrieve_crags?retrieval_kits=%5B%27gANDYgMKitDPd%2FQttLGy%2Bs7Oacnm8pfbl3Qs2UD3IS1d9wF3awJsXnjFq7OkRQE45DV4%2BMa2lDSJ5SeKEBqJK5GdPMB6CRwJ1hX7Y5SYgzpZtr%2FZ5%2FS3DHgVKn%2B8fWX92FaqEXIGcQBjYnVpbHRpbnMKc2V0CnEBXXEChXEDUnEEhnEFLg%3D%3D%27%5D&alice_verifying_key=02d3389864e9e7206ae1d18301bbd67ad8e0bdf257b3085c9aa13e9438ff9133f2&bob_encrypting_key=03d41cb7aa2df98cb9fb1591b5556363862a367faae6d0e4874a860321141788cb&bob_verifying_key=039c19e5d44b016af126d89488c4ae5599e0fde9ea30047754d1fe173d05eee468&policy_encrypting_key=02cdb2cec70b568c0624b72450c2043836aa831b06b196a50db461e87acddb791e&treasure_map=ivOS2%2FMarBpkLAksM0O%2BpgLUHAV%2F0ceIBarBKwqUpAXARhpvuwAAAm0DoDAtioScWJSHWNGzQd9pMGW2dRF4IvJX%2FExALF6AcLICLCBP%2Btte8QR4l0GLNy3YwK4oO8f8Ht0Ij%2Bv0feWWwgeo3R7FVeC4ExDuYvgdsV6jCP3vqZnLphIPk8LQeo1XVAABAtM4mGTp5yBq4dGDAbvWetjgvfJXswhcmqE%2BlDj%2FkTPyAAAB5H0rD40N1u5Ct455sh4SicbHTGsXcRSt%2FadeHVl3zylNpWDsFbeon7VI5fGGmWLAKmCJ5ARU1Mgfwg0pfsXDgHTky6XOeXnNw630z9muBE4NMUiESOQm%2FRAsphMR%2FDEIMRaCgjhaE2diVdVAm15JjRXV9JN5gAp58Y1ecPcWR2lMcgAMHBFMX60bpbgjySha94Hwb0kR2SKIFkPQnuMljoQxutTDAyh55eE2sHf9ZOAVZkpKQu8NkaWy7adx%2F1QefezNbngX9c2yYml133Al4oGrLWYA3fnbod2Y6F1oeG5As5ZIW%2FO8k7Rf%2B3i9a%2BDS1i%2BKbgETHQGxOkQSpNPUmwJjtzDJQ1xFMmKkxgwUtXenfyrzDDPU6EQloWK2PmyTD%2FhSKHLpkLyzYp95gadzDiS8RlOnNw%2FuP8vfMPSrXYGZSKXvHvlrQxKOjnF7FrheauwwRPjM0yYTftPs3jNkZwCTl%2BEwn6NdLur927SeGyAB3gHCjHenje%2B3hU1jsn%2FmwfwLJwSMT7V0rbXV6I0NYhjQy2Ajj%2B7ev%2FNSvRdeneeYTU3iHoO6nIhWHBLVExWafu59B6hhsm261kvXw718eiUcL%2B1X1eZ5WApplCuXGQV7L6DZxlQPanRJy7BZZQmFwEUoMCnx9mGbOKmNbeCADx3vwKY5nrbTDAAAAm0Cccv5a3jS2QiICCzCyA0Ot3U7VT1F3d%2BB3cHcmv8DaCwDODb8IadnsiVK%2BdfbPLn3ne%2Blm8d9yqhh6bLi6KNDb6yiWrjWnd4Irnnh3amMwik00vdyQKYvdsaSEJqtVLmtcQABAtM4mGTp5yBq4dGDAbvWetjgvfJXswhcmqE%2BlDj%2FkTPyAAAB5Do%2Feww%2BG709VPQwkxd0tRFyJh97Wcb5uSGs%2B4fK9O%2B5CTf5rDQSO3ueWLRF4ytRzd3QjK6%2B8FlXsJQM5n5pGLUNNWpUlimk2MmPaLehC9uGBfQzoTfQof%2BU8CBXkTTnRi0IeAYMq8eiuEnNR%2FoOJjpjuwgZH4gue%2FsSDF8FyhFU4SwF%2FWdjLg0FgmZzRlqABNXeE8vOofydEMYgUMPd8qxjimAGhkYlBUNjlme4BUdA2AqndMttpc3y9ILTobaGSnjgWfq9Ztw%2Fn72scPI11T%2BYMaaXd33dacNPx%2BpVzcgqi358PT8WQ6U3n%2B1be8mhF8VGEO7%2F5zLFHECRCv06erER8ChTZvr4rb8Y0xRCz%2FpatllLqvWZkGSmotmsi9qAptgG%2FXkozOZIqmBuM2AuQTwaePyuJzelc5xD51OlkQRahV6%2Bok3CokckwtOXtC6dzq4dmh03Uj5ZeKj8IgITDPN6jCf5TwLmXSuEGl5W%2FxmrEUeNlrthlJm7Cdd1NpLn3RZNCgSS4%2BPw9cpY6fj%2FmF8yR0erf9Tkrxr7FXzSe%2FUWkfeB3aQPulP4U3nM7vJIz9DBcJxtdozfqHchZ%2FK%2BVnaW%2F7IlNhvu3Cwk%2BN3D9sUwf%2FuHQuE%2FQSsYZ0fjUCnB1UgJMjho5Sd4CHLNoCFroNj71YtnpdXjUQAAAm0D5ITdM1U28%2B6%2FLU%2B%2BJw%2FUTMOefScVULkEyaojkyJK574Dc96zie3HtMN0ahALfOg5yn2z2zZpwqsLk9mpT23GD8AYR55RcvLHGIjJTubtuMINy7ZBgbZmisPDt5DvHVKj1wABAtM4mGTp5yBq4dGDAbvWetjgvfJXswhcmqE%2BlDj%2FkTPyAAAB5B9Wn5rfJ8LS81DIkZj6By39KZPYLoNSpR%2BVEZsLaSEo%2FHTMG43Q%2FgG%2FYjZMQHBEZwleE1H35P3EuDlWOriEQxveH7ihmHVSDfj8R%2B6xo%2F263QCLqtg9djSFPW7h6QRx5JBM%2BWABcmIZQrAvMDe1q7F8VOGRDMf8tW%2F7sySMFn9pQ7735kasw8iNsGPX9gVNcncSuh8hmgWGzwciUU%2FY5SYmQvl0Oc15G5%2FkFhIA9nDVfZR4sMBRB9ApYbnNYsxtH12wWhTo04hPEGfzsqKK10muLy%2Bqpo3VBhX24HPTBAvYm68f0UVD%2Ba0cZWmgYKypmMqApJ87RnPvXbE3rmKepJM8u02O4X1OBlfDZBrTsbCbMxeniS6bzE6VPE62jOW6GIuyV6%2BNQS3PZTuTWG%2Fp7T5n2EC%2FPf%2FCvGLq41gQDU9VT2aCbHkbr9C0klVJfUwqdE%2F51zLmcY8wpx3P%2BOS%2BlrIjxQzOpWSKQfsNyt1DhKpKb5Y1wWrUGm6s0sBEG7FQK2SmWMhpjB36ZRdmtQ8%2Fmvh20KELR6W%2BocGosR20TXdGINzJEnobbTkkGNz2sqzePvL7Ql5Utc%2FGCaZYC2yIvJEGBOSBVtKvwqTOaMOFTaCIx4R5f3X17umkMD1YCvir39cREkU%3D"


Example Response
++++++++++++++++
.. code::

    Status: 200 OK


.. code:: json

    {
       "result": {
          "retrieval_results": [
             {
                "capsule": "AwqK0M939C20sbL6zs5pyebyl9uXdCzZQPchLV33AXdrAmxeeMWrs6RFATjkNXj4xraUNInlJ4oQGokrkZ08wHoJHAnWFftjlJiDOlm2v9nn9LcMeBUqf7x9Zf3YVqoRcgY=",
                "cfrags": {
                   "0xd41c057fd1c78805AAC12B0A94a405c0461A6FBb": "Alvyx0r4IXvOWppw8jzbdx/8lIhL36ZAhbvNcTfo4KC6AqUxu6iP9gOVSaiehZAAQ89ho9MIGyDYdJIjg/dRkR1DuNX9qLnhAsg+qJvGcPpEXHNG0L2WHxe+AUNqtOSnwiEDegcnRTgUFyR4gfs6/M49/t8iXuXJcT6Szcwtx2JlZtACpa4KPLa5hFgI67rkiZQTqzn/aLPEzdD1zhhUyaHpJXoDfXLdpQmyEl8aI7ZOsBLh6PtPlx86/cvU0NOsR8wIoYUDe7BiAijbjo4VtcYrfvzu9CWRiWb0TQQJO6v47am/RPUD6NTr5+S/m+EvGK22L7XWtMHw7X2M380i4z2X1jxeYZaLmtuJJLAQL61kEIFv/1afCVDe+odbZ0Wivq3EiQzd0UcYRcvhIyGJdBksGv4GjfXSNNl6OCn1ny1Cn056juxGQs3yxzQZvfEN0UAOsI5IcTvOh3/kBNGfJGH+Qfv/CKc=",
                   "0x68E527780872cda0216Ba0d8fBD58b67a5D5e351": "AvGBNjTE1WrgQLkDP0ViipGoSjlaq0Plge6szUOasYsnAnB7Q0OKN52h3kyEax8bTFA8uqQ1mg8/X+ccRnda7bjyQu3Oep16gNGkNItWo0Eb7XC8ZDnAJMe6VrQMeq4l6EQDegcnRTgUFyR4gfs6/M49/t8iXuXJcT6Szcwtx2JlZtADcS7sUWM293AkLyacmHcj/ohsWrhSTqyyV8oCzVeCR9ICLqSTeEjoYyBhRseKvU+OObMv+Vi9kW68SEbHJFZhpHgC1UsJjSTGH1hpBxYUpQcaFU4O+nafk1NIQcEfDY9xKLYD2FAkkVF0OcSaeSNCcgWmBnDYY1n9lnQbF4gvumFoO91+19DjGTa/lY0e/GWI0HrZ3D7Qe8uMUD5LZIth9RHdVgT8WFrVd7Wg47/ieMPbW/zNJ0jKgnlmgcUH4v+VSvvqWCL3cqm83psyABURpMntldLubCBgTrK8vCHP/C0Aduo="
                }
             }
          ]
       },
       "version": "6.0.0"
    }
