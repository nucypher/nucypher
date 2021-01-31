=============
Lynx Testnet
=============

NuCypher provides a public Long-Term Support testnet running on the ethereum Goerli testnet as a stable playground
for application development and network users (e.g., Alices wishing to create sharing policies, grant & Retrieve, etc.).

.. note::

    Lynx testnet tokens are not needed to use nucypher as Alie, Bob, or Enrico.
    If you'd like to volunteer to run an Lynx testnet node, reach out to the
    team on our `Discord server <https://discord.gg/7rmXa3S>`_.


.. important::

    Goerli ETH is required to use the Lynx testnet.


Alice and Bob work support the lynx testnet using the python API:

.. code:: python

    # CharacterConfiguration API
    alice_factory = AliceConfiguration(domain='lynx', ...)
    alice_factory == 'lynx'
    True

    alice = alice_factory.produce()
    alice.domain == 'lynx'
    True

    # Character API
    alice = Alice(domain='lynx', ...)
    print(alice.domain)
    alice.domain == 'lynx'
    True


Alice and Bob can also be configured to use the lynx testnet using the command line:

.. code::

    # While creating a new alice
    $ nucypher alice init --network lynx --provider <GOERLI PROVIDER URI>

    # Update an existing alice
    $ nucypher alice config --network lynx --provider <GOERLI PROVIDER URI>

    # While creating a new bob
    $ nucypher bob init --network lynx --provider <GOERLI PROVIDER URI>

    # Update an existing bob
    $ nucypher bob config --network lynx --provider <GOERLI PROVIDER URI>



Deployments
-----------

* `NuCypherToken 0x02B50E38E5872068F325B1A7ca94D90ce2bfff63 <https://goerli.etherscan.io/address/0x02B50E38E5872068F325B1A7ca94D90ce2bfff63>`_
* `StakingEscrow (Dispatcher) 0x40Ca356d8180Ddc21C82263F9EbCeaAc6Cad7250 <https://goerli.etherscan.io/address/0x40Ca356d8180Ddc21C82263F9EbCeaAc6Cad7250>`_
* `PolicyManager (Dispatcher) 0xaC5e34d3FD41809873968c349d1194D23045b9D2 <https://goerli.etherscan.io/address/0xaC5e34d3FD41809873968c349d1194D23045b9D2>`_
* `Adjudicator (Dispatcher) 0xC62e20B599416e4B5F3b54d50837F070bFec6412 <https://goerli.etherscan.io/address/0xC62e20B599416e4B5F3b54d50837F070bFec6412>`_
