=================
Deployment Guide
=================

Geth Development Deployment
---------------------------

The fastest way to start a local private chain using an ethereum client is
to deploy a single-host network with the geth CLI.

.. code:: bash

    $ geth --dev
      ...

*In another terminal*

.. code:: bash

    (nucypher)$ nucypher-deploy contracts --provider-uri ipc:///tmp/geth.ipc --poa
    ...

This will deploy the main NuCypher contracts: NuCypherToken, MinerEscrow, PolicyManager,
along with their proxies, as well as executing initialization transactions. You will need to enter
the contract's upgrade secrets, which can be any alphanumeric string.

A summary of deployed contract addresses, transactions, and gas usage will be displayed on success, and a
`contract_registry.json` file will be generated in your nucypher application directory.

.. code:: bash

    Deployer Address is 0xB62CD782B3c73b1213fbba6ee72e6eaeEC2B327d - Continue? [y/N]:

    Enter MinerEscrow Deployment Secret:
    Repeat for confirmation:
    Enter PolicyManager Deployment Secret:
    Repeat for confirmation:
    Enter UserEscrowProxy Deployment Secret:
    Repeat for confirmation:

    Deployed!

    Deployment Transaction Hashes for /home/kieran/.local/share/nucypher/contract_registry.json

    NuCypherToken (0x2d610671e756dbE547a9b9Dc9A46d6A90Ac9C08c)
    **********************************************************
    OK | txhash | 0xd1f4a35a9cf46456c38b4ab5f978ab4d70ce1979016e4c60d155f7112ca4538c (793804 gas)
    Block #2 | 0x610cf940169d8e92b6f363daef36719643a79cdfa63b961ef8147513aef8855f


    MinersEscrow (0xca6b01013336065456f0ac0Dd98Ae6F3F786C0d2)
    *********************************************************
    OK | deploy | 0x9b1842bd08c680f8cfd3734722fea9118a582a55026d23fd8ad10af08996c27d (5266629 gas)
    Block #3 | 0x5d8c9daf95ad42ada2ab7a6645b59b7d778fc15fce2b19f73bcab78e8d41ffac

    OK | dispatcher_deploy | 0x9e7d6420e58f9487923af6a92f34f379ea0b2333ba372324cb9ec73ba02b6193 (1184911 gas)
    Block #4 | 0x337c2f77b4f5b18d4ecfdae171dbd9c53aed74d7ddf85f0d82f569e8a9544182

    OK | reward_transfer | 0xc1a56af5e8f2961f6808a3d3de25ebc71f3aec10097ad6ac063c2416d6cf2a85 (51860 gas)
    Block #5 | 0x1617cc77c2e9b159903c3d7a43f0f98a652d961168d48c23106a15860309c49f

    OK | initialize | 0x78064a72b5e79caf957dbb24ab9277ffb269526d2ce4cb0fdb7390048b69e643 (95553 gas)
    Block #6 | 0xc74846b426a44f2148d62207960da7e746c0de31be323368cd6afcc3a308a244


    PolicyManager (0x124Bb5a44D2AcCB811Af8aab889F65DfCb2f9858)
    **********************************************************
    OK | deployment | 0x6afe2b645d6d9158ad79a0bc10c52e462eb33b18a3e9bbb1a99484888c3ecffb (2756954 gas)
    Block #7 | 0x9590d75afdfaa5ed30d77621bf265fdaee8e366ae9fce2c1a25d6903f27a3ed3

    OK | dispatcher_deployment | 0x06d1399bd49e2f1afa72342866100b2281df110f36420b663df10b8e956c76de (1277565 gas)
    Block #8 | 0xe6714a7cdb74e3025a64c3f5d077994664ee3c4e1ed6c71cca336ce2781edbd2

    OK | set_policy_manager | 0x9981edb9d7d54db8c6735ee802c19a153b071e798e58bae38dcf1346ea28fa1e (50253 gas)
    Block #9 | 0xe70a8252a4899fb4dd1f7a4c0f7d12933f7c321ae6c784b777c668a5d8494563

    Cumulative Gas Consumption: 4084772 gas
