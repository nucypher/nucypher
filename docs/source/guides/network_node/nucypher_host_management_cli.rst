.. _managing-cloud-workers:

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
|  ``up``              | Creates and deploys hosts for all active local stakers.                       |
+----------------------+-------------------------------------------------------------------------------+
|  ``create``          | Creates and deploys the given number of hosts independent of stakes           |
+----------------------+-------------------------------------------------------------------------------+
|  ``add``             | Add an existing host to be managed by cloudworkers CLI tools                  |
+----------------------+-------------------------------------------------------------------------------+
|  ``add_for_stake``   | Add an existing host to be managed for a specified local staker address       |
+----------------------+-------------------------------------------------------------------------------+
|  ``deploy``          | Install and run Ursula on existing managed hosts.                             |
+----------------------+-------------------------------------------------------------------------------+
|  ``update``          | Update or manage existing installed Ursula.                                   |
+----------------------+-------------------------------------------------------------------------------+
|  ``destroy``         | Shut down and cleanup resources deployed on AWS or Digital Ocean              |
+----------------------+-------------------------------------------------------------------------------+
|  ``stop``            | Stop the selected nodes.                                                      |
+----------------------+-------------------------------------------------------------------------------+
|  ``status``          | Prints a formatted status of selected managed hosts.                          |
+----------------------+-------------------------------------------------------------------------------+
|  ``logs``            | Download and display the accumulated stdout logs of selected hosts            |
+----------------------+-------------------------------------------------------------------------------+
|  ``backup``          | Download local copies of critical data from selected installed Ursulas        |
+----------------------+-------------------------------------------------------------------------------+
|  ``restore``         | Reconstitute and deploy an operating Ursula from backed up data               |
+----------------------+-------------------------------------------------------------------------------+
|  ``list_hosts``      | Print local nicknames of all managed hosts under a given namespace            |
+----------------------+-------------------------------------------------------------------------------+
|  ``list_namespaces`` | Print namespaces under a given network                                        |
+----------------------+-------------------------------------------------------------------------------+


Some examples:

.. code:: bash

    # You have some local stakes.  Now run an Ursula for each one with a single command.

    # on Digital Ocean
    $ export DIGITALOCEAN_ACCESS_TOKEN=<your access token>
    $ export DIGITALOCEAN_REGION=<a digitalocean availability region>
    $ nucypher cloudworkers up --cloudprovider digitalocean --remote-provider http://mainnet.infura..3epifj3rfioj

    # --------------------------------------------------------------------------------------------------------------------------- #
    # NOTE:  if no --remote-provider is specified, geth will be run on the host and a larger instance with more RAM will be used.
    # this will probably cost more and require some time to sync.  * A remote provider such as Alchemy or Infura is highly recommended *
    # --------------------------------------------------------------------------------------------------------------------------- #

    # on AWS
    # configure your local aws cli with named profiles https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html
    $ nucypher cloudworkers up --cloudprovider aws --aws-profile my-aws-profile --remote-provider http://mainnet.infura..3epifj3rfioj

    # add your ubuntu machine at the office to an existing locally managed stake
    $ nucypher cloudworkers add_for_stake --staker-address 0x9a92354D3811938A1f35644825188cAe3103bA8e --host-address somebox.myoffice.net --login-name ubuntu --key-path ~/.ssh/id_rsa

    # update all your existing hosts to the latest code
    $ nucypher cloudworkers update --nucypher-image nucypher/nucypher:latest

    # stop the running Ursula on your hosts
    $ nucypher cloudworkers stop

    # change two of your existing hosts to use alchemy instead of infura as a delegated blockchain
    # note: hosts created for local stakers will have the staker's checksum address as their nickname by default
    $ nucypher cloudworkers update --remote-provider wss://eth-mainnet.ws.alchemyapi.io/v2/aodfh298fh2398fh2398hf3924f... --include-host 0x9a92354D3811938A1f35644825188cAe3103bA8e --include-host 0x1Da644825188cAe3103bA8e92354D3811938A1f35

    # add some random host and then deploy an Ursula on it
    $ nucypher cloudworkers add --host-address somebox.myoffice.net --login-name ubuntu --key-path ~/.ssh/id_rsa --nickname my_new_host
    $ nucypher cloudworkers deploy --include-host my_new_host --remote-provider http://mainnet.infura..3epifj3rfioj

    # deploy nucypher on all your managed hosts
    $ nucypher cloudworkers deploy --remote-provider http://mainnet.infura..3epifj3rfioj

    # deploy nucypher on all your managed hosts
    $ nucypher cloudworkers deploy --remote-provider http://mainnet.infura..3epifj3rfioj

    # print the current status of all workers across all namespaces (in bash)
    $ for ns in $(nucypher cloudworkers list-namespaces); do nucypher cloudworkers status --namespace $ns; done
    > local nickname: Project11-mainnet-2
    >  nickname: Aquamarine Nine DarkViolet Foxtrot
    >  staker address:          0xFBC052299b8B3Df05CB8351151E71f21562096F4
    >  worker address:          0xe88bF385a6ed8C86aA153f08F999d8698B5326e0
    >  rest url:                https://xxx.xxx.xxx.xxx:9151
    >      missing commitments:   0
    >      last committed period: 18601
    >      ETH:                   0.xxx
    >      provider:              https://mainnet.infura.io/v3/xxxx
    >      ursula docker image:   "nucypher/nucypher:latest"
    >      ursula command:        ""nucypher ursula run --network mainnet""
    >      last log line:         Working ~ Keep Ursula Online!
    .....

    # see if all your managed hosts successfully committed to the next period
    $ for ns in $(nucypher cloudworkers list-namespaces); do nucypher cloudworkers status --namespace $ns; done | grep "last committed period: \|last log line: \|local nickname:"

    # backup all your worker's critical data
    # note: this is also done after any update or deploy operations
    $ for ns in $(nucypher cloudworkers list-namespaces); do nucypher cloudworkers backup --namespace $ns; done

    # show some info about your hosts
    $ nucypher cloudworkers list-hosts -v

    # set a max-gas-price for existing hosts
    $ nucypher cloudworkers update --cli max-gas-price=50

    # NB: environment variables and cli args function identically for both update and deploy

    # set some environment variables to configure Ursula workers on all your hosts
    $ nucypher cloudworkers deploy -e DONT_PERFORM_WORK_ON_SUNDAY=true

    # set a max gas price and gas strategy for existing hosts
    $ nucypher cloudworkers update --cli max-gas-price=50 --cli gas-strategy=slow
