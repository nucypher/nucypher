    .. _managing-cloud-nodes:

===============================
PRE Node Deployment Automation
===============================

.. note::

    Previously this functionality was provided by the ``nucypher cloudworkers`` CLI command.
    However, that command has been deprecated and analogous functionality is now provided
    via `nucypher-ops <https://github.com/nucypher/nucypher-ops>`_.


In this tutorial we're going to setup a Threshold PRE node using a remote cloud provider (Digital Ocean, AWS, and more in the future).
The PRE node will run via a Docker container.

.. note::

    By default, ``nucypher-ops`` uses a Docker container restart policy of ``unless-stopped``.
    This ensures that the Docker container will be automatically restarted if it exited,
    except if the container was stopped via an appropriate command. See `Docker Restart Policies <https://docs.docker.com/engine/reference/run/#restart-policies---restart>`_
    for more information.

This example will demonstrate how to deploy to Digital Ocean. There are a few pre-requisites before we can get started.
First, we need to create accounts on `Digital Ocean <https://cloud.digitalocean.com/>`_ and `Infura <https://infura.io>`_.
Also ensure that your local environment has python 3.8 or later installed.


Launch Remote Node
-------------------

.. important::

    nucypher-ops requires python 3.8 or later.

Locally, we will install `NuCypher Ops <https://github.com/nucypher/nucypher-ops>`_ to handle the heavy lifting of setting up a node.

.. code-block:: bash

    $ pip install nucypher-ops

Now NuCypher Ops is installed we can create a droplet on Digital Ocean:

.. code-block:: bash

    nucypher-ops nodes create

Follow the interactive prompts to select the Digital Ocean provider.
After this command completes you will see a new droplet in your Digital Ocean dashboard.
Now we can deploy the PRE Node:

.. code-block:: bash

    nucypher-ops ursula deploy

Follow the prompts to enter your ethereum and polygon provider URIs.

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

Stake and Bond
--------------

If you have not already done so you'll need to establish a stake on the `Threshold
Dashboard <https://dashboard.threshold.network/overview/network>`_.
After you've established your stake, proceed to the
`PRE node bonding dashboard <https://stake.nucypher.network/manage/operator>`_ to bond your node's
Operator address to your stake.


Monitor Remote Node
-------------------

Send a small amount of ETH to your Operator address so it can perform the initial confirmation transaction which signals that your
node is open for business. Once you've funded the Operator address and bonded to the stake, view the node's logs.
It will automatically detect both completed actions.

After funding and bonding the node will resume startup displaying the following logs:

.. code-block:: bash

    Broadcasting CONFIRMOPERATORADDRESS Transaction (0.00416485444 ETH @ 88.58 gwei)
    TXHASH 0x3329exxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5ec9a6
    ✓ Work Tracking
    ✓ Start Operator Bonded Tracker
    ✓ Rest Server https://123.456.789.000:9151
    Working ~ Keep Ursula Online!

You can view the status of your node by visiting ``https://<YOUR_NODE_IP>:9151/status``

That's all!
