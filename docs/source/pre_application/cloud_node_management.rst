.. _managing-cloud-nodes:

PRE Node Cloud Automation
=========================

.. important::

    In order to run a PRE node on Threshold, ``nucypher`` version 6.0.0 is required,
    but is not yet available. See `releases <https://pypi.org/project/nucypher/#history>`_.

    However, this documentation can be used in the interim to gain a better understanding of
    the logistics of running a PRE node.


NuCypher maintains a CLI to assist with the initialization and management of PRE nodes
deployed on cloud infrastructure, that leverages automation tools
such as `Ansible <https://www.ansible.com/>`_ and `Docker <https://www.docker.com/>`_.

.. important::

    Only supports Digital Ocean and AWS cloud infrastructure.

This tool will handle the minutiae of node configuration and operation on your behalf by
providing high-level CLI commands.


.. code:: bash

    (nucypher)$ nucypher cloudworkers ACTION [OPTIONS]

**Command Actions**

+----------------------+-------------------------------------------------------------------------------+
| Action               |  Description                                                                  |
+======================+===============================================================================+
|  ``up``              | Creates and deploys hosts for stakers.                                        |
+----------------------+-------------------------------------------------------------------------------+
|  ``create``          | Creates and deploys the given number of hosts independent of stakes           |
+----------------------+-------------------------------------------------------------------------------+
|  ``add``             | Add an existing host to be managed by cloudworkers CLI tools                  |
+----------------------+-------------------------------------------------------------------------------+
|  ``add_for_stake``   | Add an existing host to be managed for a specified staker                     |
+----------------------+-------------------------------------------------------------------------------+
|  ``deploy``          | Install and run a node on existing managed hosts.                             |
+----------------------+-------------------------------------------------------------------------------+
|  ``update``          | Update or manage existing installed nodes.                                    |
+----------------------+-------------------------------------------------------------------------------+
|  ``destroy``         | Shut down and cleanup resources deployed on AWS or Digital Ocean              |
+----------------------+-------------------------------------------------------------------------------+
|  ``stop``            | Stop the selected nodes.                                                      |
+----------------------+-------------------------------------------------------------------------------+
|  ``status``          | Prints a formatted status of selected managed hosts.                          |
+----------------------+-------------------------------------------------------------------------------+
|  ``logs``            | Download and display the accumulated stdout logs of selected hosts            |
+----------------------+-------------------------------------------------------------------------------+
|  ``backup``          | Download local copies of critical data from selected installed nodes          |
+----------------------+-------------------------------------------------------------------------------+
|  ``restore``         | Reconstitute and deploy an operating node from backed up data                 |
+----------------------+-------------------------------------------------------------------------------+
|  ``list_hosts``      | Print local nicknames of all managed hosts under a given namespace            |
+----------------------+-------------------------------------------------------------------------------+
|  ``list_namespaces`` | Print namespaces under a given network                                        |
+----------------------+-------------------------------------------------------------------------------+


Some examples:

.. code:: bash

    #
    # Initialize a node
    #

    # on Digital Ocean
    ##################
    $ export DIGITALOCEAN_ACCESS_TOKEN=<your access token>
    $ export DIGITALOCEAN_REGION=<a digitalocean availability region>
    $ nucypher cloudworkers up --cloudprovider digitalocean --remote-provider http://mainnet.infura..3epifj3rfioj

    # OR

    # on AWS
    ########
    # configure your local aws cli with named profiles https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html
    $ nucypher cloudworkers up --cloudprovider aws --aws-profile my-aws-profile --remote-provider https://mainnet.infura..3epifj3rfioj


    ####################################################################################################################################
    #
    # Management Commands
    #

    # add your ubuntu machine to an existing stake
    $ nucypher cloudworkers add_for_stake --staker-address 0x9a92354D3811938A1f35644825188cAe3103bA8e --host-address somebox.myoffice.net --login-name ubuntu --key-path ~/.ssh/id_rsa

    # update all your existing hosts to the latest code
    $ nucypher cloudworkers update --nucypher-image nucypher/nucypher:latest

    # stop the running node(s) on your host(s)
    $ nucypher cloudworkers stop

    # change two of your existing hosts to use alchemy instead of infura as a delegated blockchain
    # note: hosts created for local stakers will have the staker's checksum address as their nickname by default
    $ nucypher cloudworkers update --remote-provider https://eth-mainnet.ws.alchemyapi.io/v2/aodfh298fh2398fh2398hf3924f... --include-host 0x9a92354D3811938A1f35644825188cAe3103bA8e --include-host 0x1Da644825188cAe3103bA8e92354D3811938A1f35

    # add some random host and then deploy a node on it
    $ nucypher cloudworkers add --host-address somebox.myoffice.net --login-name ubuntu --key-path ~/.ssh/id_rsa --nickname my_new_host
    $ nucypher cloudworkers deploy --include-host my_new_host --remote-provider https://mainnet.infura..3epifj3rfioj

    # deploy nucypher on all your managed hosts
    $ nucypher cloudworkers deploy --remote-provider https://mainnet.infura..3epifj3rfioj

    # deploy nucypher on all your managed hosts
    $ nucypher cloudworkers deploy --remote-provider https://mainnet.infura..3epifj3rfioj

    # print the current status of all nodes across all namespaces (in bash)
    $ for ns in $(nucypher cloudworkers list-namespaces); do nucypher cloudworkers status --namespace $ns; done
    > local nickname: Project11-mainnet-2
    >  nickname: Aquamarine Nine DarkViolet Foxtrot
    >  staker address:          0xFBC052299b8B3Df05CB8351151E71f21562096F4
    >  worker address:          0xe88bF385a6ed8C86aA153f08F999d8698B5326e0
    >  rest url:                https://xxx.xxx.xxx.xxx:9151
    >      missing commitments:   0
    >      last committed period: 2657
    >      ETH:                   0.xxx
    >      provider:              https://mainnet.infura.io/v3/xxxx
    >      ursula docker image:   "nucypher/nucypher:latest"
    >      ursula command:        ""nucypher ursula run --network mainnet""
    >      last log line:         Working ~ Keep Ursula Online!
    .....

    # see if all your managed hosts successfully committed to the next period
    $ for ns in $(nucypher cloudworkers list-namespaces); do nucypher cloudworkers status --namespace $ns; done | grep "last committed period: \|last log line: \|local nickname:"

    # backup all your node's critical data
    # note: this is also done after any update or deploy operations
    $ for ns in $(nucypher cloudworkers list-namespaces); do nucypher cloudworkers backup --namespace $ns; done

    # show some info about your hosts
    $ nucypher cloudworkers list-hosts -v

    # set a max-gas-price for existing hosts
    $ nucypher cloudworkers update --cli max-gas-price=50

    # NB: environment variables and cli args function identically for both update and deploy

    # set some environment variables to configure nodes on all your hosts
    $ nucypher cloudworkers deploy -e DONT_PERFORM_WORK_ON_SUNDAY=true

    # set a max gas price and gas strategy for existing hosts
    $ nucypher cloudworkers update --cli max-gas-price=50 --cli gas-strategy=slow
