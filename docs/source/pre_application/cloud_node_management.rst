.. _managing-cloud-nodes:

===============================
PRE Node Deployment Automation
===============================

.. note::

    Previously this functionality was provided by the ``nucypher cloudworkers`` CLI command.
    However, that command has been deprecated and analogous functionality is now provided
    via `nucypher-ops <https://github.com/nucypher/nucypher-ops>`_.


In this tutorial we're going to setup a Threshold PRE Node using a remote cloud provider (Digital Ocean, AWS, and more in the future).
Whilst this example will demonstrate how to deploy to Digital Ocean, the steps for any other infrastructure provider are virtually identical.
There are a few pre-requisites before we can get started.
First, we need to create accounts at `Digital Ocean <https://cloud.digitalocean.com/>`_ and `Infura <https://infura.io>`_.

In order to run a node will also need to have an existing Threshold stake.  For more information see


Digital Ocean
-------------
All of the Digital Ocean configuration will be done automatically, but there are two local environment variables we need to set in order to make this work:

- ``DIGITALOCEAN_ACCESS_TOKEN`` - your Digital Ocean `access token <https://docs.digitalocean.com/reference/api/create-personal-access-token/>`_.
- ``DIGITAL_OCEAN_KEY_FINGERPRINT`` - your Digital Ocean `key fingerprint <https://docs.digitalocean.com/products/droplets/how-to/add-ssh-keys/to-account/>`_.

Follow those two blog posts and either ``export`` the environment variables or add them to your ``~/.bashrc`` file.


Infura
------
We need a way to interact with both the Ethereum and Polygon networks; Infura makes this easy for us.
Create a new project at Infura with product type ``ETHEREUM``.
Also, add the Polygon add-on to this project.
We're going to create two more environment variables:

- ``INFURA_MAINNET_URL``
- ``INFURA_POLYGON_URL``

In the **Project Settings**, change the ``ENDPOINTS`` to ``MAINNET`` / ``POLYGON``.
Set the above environment variables to the corresponding ``https`` endpoint.


Overall the environment variable process should look something like:

.. code-block:: bash

    $ export INFURA_MAINNET_URL=https://mainnet.infura.io/v3/bd76baxxxxxxxxxxxxxxxxxxxxxf0ff0
    $ export INFURA_POLYGON_URL=https://polygon.infura.io/v3/bd76baxxxxxxxxxxxxxxxxxxxxxf0ff0
    $ export DIGITALOCEAN_ACCESS_TOKEN=4ade7a8701xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxbafd23
    $ export DIGITAL_OCEAN_KEY_FINGERPRINT=28:38:e7xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx:ca:5c


Setup Remote Node
-----------------
Locally, we will install `NuCypher Ops <https://github.com/nucypher/nucypher-ops>`_ to handle the heavy lifting of setting up a node.

.. code-block:: bash

    $ pip install nucypher-ops

Now NuCypher Ops is installed we can create a droplet on Digital Ocean:

.. code-block:: bash

    nucypher-ops nodes create --network mainnet --count 1 --cloudprovider digitalocean

At this point you should see the droplet in your Digital Ocean dashboard.
Now we can deploy the PRE Node:

.. code-block:: bash

    nucypher-ops ursula deploy --eth-provider $INFURA_MAINNET_URL --nucypher-image nucypher/nucypher:latest --payment-provider $INFURA_POLYGON_URL --network mainnet

This should produce a lot of log messages as the ansible playbooks install all the requirements and setup the node.
The final output should be similar to:

.. code-block:: bash

    some relevant info:
    config file: "/SOME_PATH/nucypher-ops/configs/mainnet/nucypher/mainnet-nucypher.json"
    inventory file: /SOME_PATH/nucypher-ops/configs/mainnet-nucypher-2022-03-25.ansible_inventory.yml
    If you like, you can run the same playbook directly in ansible with the following:
        ansible-playbook -i "/SOME_PATH/nucypher-ops/configs/mainnet-nucypher-2022-03-25.ansible_inventory.yml" "src/playbooks/setup_remote_workers.yml"
    You may wish to ssh into your running hosts:
        ssh root@123.456.789.xxx
    *** Local backups containing sensitive data may have been created. ***
    Backup data can be found here: /SOME_PATH//nucypher-ops/configs/mainnet/nucypher/remote_worker_backups/

This tells us the location of several config files and helpfully prints the IP address of our newly created node (you can also see this on the Digital Ocean dashboard).
Let's ``ssh`` into it and look at the logs:

.. code-block:: bash

    $ ssh root@123.456.789.xxx
    root@nucypher-mainnet-1:~#
    root@nucypher-mainnet-1:~# sudo docker logs --follow ursula
    ...
    ! Operator 0x06E11400xxxxxxxxxxxxxxxxxxxxxxxxxxxx1Fc0 is not funded with ETH
    ! Operator 0x06E11400xxxxxxxxxxxxxxxxxxxxxxxxxxxx1Fc0 is not bonded to a staking provider
    ...

These lines will print repeatedly until the Operator is funded with some mainnet ETH and bonded to a staking provider.
Send mainnet ETH to the operator address that is printed

Once you've funded and staking transaction is confirmed, view the logs of the node. You should see:

.. code-block:: bash

    Broadcasting CONFIRMOPERATORADDRESS Transaction (0.00416485444 ETH @ 88.58 gwei)
    TXHASH 0x3329exxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5ec9a6
    ✓ Work Tracking
    ✓ Start Operator Bonded Tracker
    ✓ Rest Server https://123.456.789.000:9151
    Working ~ Keep Ursula Online!

You can view the status of your node by visiting ``https://YOUR_NODE_IP:9151/status``
