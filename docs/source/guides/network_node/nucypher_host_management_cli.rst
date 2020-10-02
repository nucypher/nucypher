.. _running-a-node:

===================================================
Nucypher CLI tools for running and managing workers
===================================================

Cloudworkers CLI
----------------

Nucypher maintains some simple tools leveraging open source tools such as Ansible, to make it easy
to keep your Nucypher Ursula nodes working and up to date.

.. code:: bash

    (nucypher)$ nucypher cloudworkers ACTION [OPTIONS]

**Cloudworkers Command Actions**

+----------------------+-------------------------------------------------------------------------------+
| Action               |  Description                                                                  |
+======================+===============================================================================+
|  ``up``              | Create hosts, configure and deploy an Ursula on AWS or Digital Ocean          |
+----------------------+-------------------------------------------------------------------------------+
|  ``add``             | Add an existing host to be managed by cloudworkers CLI tools                  |
+----------------------+-------------------------------------------------------------------------------+
|  ``deploy``          | Update and deploy Ursula on existing hosts.                                   |
+----------------------+-------------------------------------------------------------------------------+
|  ``destroy``         | Shut down and cleanup resources deployed on AWS or Digital Ocean              |
+----------------------+-------------------------------------------------------------------------------+
|  ``status``          | Query the status of all managed hosts.                                        |
+----------------------+-------------------------------------------------------------------------------+


Some examples:

.. code:: bash

    # You have created stakes already.  Now run an Ursula for each one

    # on Digital Ocean
    $ export DIGITALOCEAN_ACCESS_TOKEN=<your access token>
    $ export DIGITALOCEAN_REGION=<a digitalocean availability region>
    $ nucypher cloudworkers up --cloudprovider digitalocean --remote-provider http://mainnet.infura..3epifj3rfioj

    # on AWS
    $ nucypher cloudworkers up --cloudprovider aws --aws-profile my-aws-profile --remote-provider http://mainnet.infura..3epifj3rfioj

    # add your ubuntu machine at the office
    $ nucypher cloudworkers add --staker-address 0x9a92354D3811938A1f35644825188cAe3103bA8e --host-address somebox.myoffice.net --login-name root --key-path ~/.ssh/id_rsa

    # deploy or update all your existing hosts to the latest code
    $ nucypher cloudworkers deploy --nucypher-image nucypher/nucypher:latest
