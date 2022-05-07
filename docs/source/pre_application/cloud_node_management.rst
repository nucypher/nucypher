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
There are a few pre-requisites before we can get started. First, we need to create accounts at `Digital Ocean <https://cloud.digitalocean.com/>`_ and `Infura <https://infura.io>`_.


Launch Remote Node
-------------------
Locally, we will install `NuCypher Ops <https://github.com/nucypher/nucypher-ops>`_ to handle the heavy lifting of setting up a node.

.. code-block:: bash

    $ pip install nucypher-ops

Now NuCypher Ops is installed we can create a droplet on Digital Ocean:

.. code-block:: bash

    nucypher-ops nodes create

At this point you should see the droplet in your Digital Ocean dashboard.
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
Send mainnet ETH to the operator address that is printed.


Stake an Bond
-------------

If you have not already done so you'll need to establish a stake on the threshold
staking dashboard ``https://dashboard.threshold.network/overview/network``.
After you've established your stake, proceed to the PRE node bonding dashboard to bond your node's
operator address to your stake. ``https://stake.nucypher.network/manage/operator``.


Monitor Remote Node
-------------------

Send a small amount of ETH to your operator address so it can perform the initial start transaction which signals that your
node is open for business. Once you've funded and your staking transaction is confirmed, view the logs of the node.
It will automatically detect that you have staked.  You should see:

.. code-block:: bash

    Broadcasting CONFIRMOPERATORADDRESS Transaction (0.00416485444 ETH @ 88.58 gwei)
    TXHASH 0x3329exxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5ec9a6
    ✓ Work Tracking
    ✓ Start Operator Bonded Tracker
    ✓ Rest Server https://123.456.789.000:9151
    Working ~ Keep Ursula Online!

You can view the status of your node by visiting ``https://YOUR_NODE_IP:9151/status``

That's all!
