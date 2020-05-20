..
   TODO: #1354 - Find a home for this guide

:orphan:

=================
Deployment Guide
=================

Geth Development Deployment
---------------------------

The fastest way to start a local private chain using an Ethereum client is
to deploy a single-host network with the geth CLI, using the ``--dev`` flag.
Additional flags can be set up to increase the block gas limit.

.. code:: bash

    $ geth --dev --dev.period 3 --targetgaslimit 8000000
      ...

*In another terminal*

.. code:: bash

    (nucypher)$ nucypher-deploy contracts --provider ipc:///tmp/geth.ipc
    ...

This will deploy the main NuCypher contracts, namely ``NuCypherToken``, ``StakingEscrow``, ``PolicyManager`` and ``Adjudicator``,
along with their proxies (or ``Dispatchers``), as well as executing initialization transactions.

A summary of deployed contract addresses, transactions, and gas usage will be displayed on success, and a
``contract_registry.json`` file will be generated in your nucypher application directory.

.. code:: bash

    Using contract registry filepath /Users/david/nucypher/contract_registry.json

    0 | 0x53Ecb3C7AFc7D5337a89CBd792398cd4DfAc7CE0
    Select deployer account [0]: 0
    Selected 0x53Ecb3C7AFc7D5337a89CBd792398cd4DfAc7CE0 - Continue? [y/N]: y

    Deployer ETH balance: 115792089237.31



    ███╗   ██╗██╗   ██╗
    ████╗  ██║██║   ██║
    ██╔██╗ ██║██║   ██║
    ██║╚██╗██║██║   ██║
    ██║ ╚████║╚██████╔╝
    ╚═╝  ╚═══╝ ╚═════╝


    Current Time ........ 2019-08-13T10:03:41.073328Z
    Web3 Provider ....... ipc:///tmp/geth.ipc
    Block ............... 44
    Gas Price ........... 1
    Deployer Address .... 0x53Ecb3C7AFc7D5337a89CBd792398cd4DfAc7CE0
    ETH ................. 115792089237.31
    Chain ID ............ 1337
    Chain Name .......... GethDev

    Deployment successfully staged. Take a deep breath.

    Type 'DEPLOY' to continue: DEPLOY
    Starting deployment in 3 seconds...
    2...
    1...
    0...

    Deploying NuCypherToken ...

    NuCypherToken (0xC89FA1a3841F81ac3deCE8e418AafCA6c1CD94a8)
    **********************************************************
    OK | contract_deployment | 0x98cc0990659b4f979552847225cdb56794ddca2519e4d4b245a2b7219408bc96 (793932 gas)
    Block #48 | 0xc3f63772bf84452e0dc7d280aa49885a4e20b765fe39e7258cb4338d76818bdd

    Press any key to continue with deployment of StakingEscrow

    Deploying StakingEscrow ...

    StakingEscrow (0x14bb65d540215240aB295Cf2BEB1B623C9FdB36e)
    **********************************************************
    OK | contract_deployment | 0x9e420ec1a4256d1a8e39cae57577883e01da0cfe1d69bf6b90350321f4be8bdc (6331314 gas)
    Block #51 | 0x850d06f7aaa53005c127ad44c7e352a01743f7cbb0180c8d842bca04be8d8270
    OK | dispatcher_deployment | 0x85ddc4a749b053bcf407b50940eb4a9912c5f3a10ab4081b240c3e3bae0139b2 (1358900 gas)
    Block #53 | 0xf3c0a6b99c4ad6ab23a5febf20a0c70ef51cd1557ca2fee00c4b56512786b6c1
    OK | reward_transfer | 0x7d2e53365195eb9748be4ee0423b1408688369624108a3e0a84cfb54bc5fb33b (51988 gas)
    Block #55 | 0xad070b1ddf40011eda8dd09b0dc7f2f91f5698336d436cfd8c2e3ee47d33f096
    OK | initialize | 0xdde2275fbc5b82f5515e40962327fa375e35fdd1b17581e3146d01d6106ea235 (96621 gas)
    Block #57 | 0xc9c75045ff862cd48bf1640f69bf62d3800ee2b14988dde61c2a34cc22a6cc61

    Press any key to continue with deployment of PolicyManager

    Deploying PolicyManager ...

    PolicyManager (0xaBcac1AFDAFB948CF33631d9aa56D1dAB96a5af0)
    **********************************************************
    OK | deployment | 0xfdef64fa667e647bd99ac242e97949f3997eb76195207b20928c1c1b191e456f (2828689 gas)
    Block #60 | 0x9d5a61cbb575ce5142f6903e8b9ec276f49fa9a4881f782b1fc4c5effdcfd685
    OK | dispatcher_deployment | 0x67797a22f9b40132fe25cd43f49e8f8e7aabfba7c1dc332967645113cd71926f (1406994 gas)
    Block #62 | 0xea1fe477fe34b827b1c09a48724873b39b310cda48bf3c8ef8dd66fabc6673fd
    OK | set_policy_manager | 0x43608517bd064b93a81affe4f9bdaea86262a457e031c55a176cf0ba9faab3b2 (51556 gas)
    Block #64 | 0xc5d70ae626ec708e3a785f18710f135be8d0aaaffc56dc33f6daa6d3b7a96ed4

    Press any key to continue with deployment of StakingInterface

    Deploying StakingInterface ...

    StakingInterface (0x45e32FFf386Ace887474F66dCcc719628E27f2C8)
    ************************************************************
    OK | contract_deployment | 0xb66d0350ec6c33ef287e1967977600c97166021328557fad5a0c6f47115594fd (1302643 gas)
    Block #66 | 0xa89f9f6411af7e5f1cd20e9cceff55a5d90fb6c0fbcc7856b9cc75aa7bb93094
    OK | router_deployment | 0x1b29376235954d08edaca80c4537f27ae582299e812f5c9affe828a26cea3103 (395961 gas)
    Block #68 | 0x4a08ff8a47cef9de42aa8488ab5f8e03adf27d8959ad62604897143a2504e186

    Press any key to continue with deployment of Adjudicator

    Deploying Adjudicator ...

    Adjudicator (0x1C86f8A1765Bd982fAE78FD4e422d8110D043D26)
    ********************************************************
    OK | contract_deployment | 0xf78b8e683a815022b9ad86c2957749970098a74569209500672aa69ca5756b39 (4607080 gas)
    Block #71 | 0x997c17d74996f3f944388032c5b75809e5eea193e92357de1985480e879e60d0
    OK | dispatcher_deployment | 0xde8fc7493dd07275068071a768bd9d247673bb1f0218dcb4764f077887d8aabc (1289973 gas)
    Block #73 | 0x1b5c924595ca35b27ca4aa0289d5140ff91e1a45b5d2d3157a4073c428c9c098
    OK | set_adjudicator | 0xe7a37ce05b271ba0c7aae1ac514e8d7160093edbf16f63a1e322b85c6c1ca971 (51576 gas)
    Block #75 | 0x51f247092d2525a8c4f93f8fc4ae4a2ea392bb1a871146cb8476bc86dc62de0b

    Generated registry /Users/david/nucypher/contract_registry.json
    Saved deployment receipts to /Users/david/nucypher/deployment-receipts-0x53Ec-1565690714.json
