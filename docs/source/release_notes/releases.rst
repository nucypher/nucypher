========
Releases
========

.. towncrier release notes start

v4.1.2 (2020-11-09)
-------------------

Features
~~~~~~~~

- Added support for a user-provided gas price to the ``nucypher stake`` command, using ``--gas-price GWEI``. (`#2425 <https://github.com/nucypher/nucypher/issues/2425>`__)


Bugfixes
~~~~~~~~

- Correct CLI problems when setting the min fee rate. Also, simplifies usage by expressing rates in GWEI. (`#2390 <https://github.com/nucypher/nucypher/issues/2390>`__)
- Tone-down learning logging messages even more (see issue #1712). Fixes some CLI and exception messages. (`#2395 <https://github.com/nucypher/nucypher/issues/2395>`__)
- Fixes logical bug in ``WorkTracker`` to ensure commitment transactions can only be issued once per period. (`#2406 <https://github.com/nucypher/nucypher/issues/2406>`__)
- Removes leftover imports of Twisted Logger, using instead our shim (Closes #2404). Also, changes NuCypher Logger behavior to always escape curly braces. (`#2412 <https://github.com/nucypher/nucypher/issues/2412>`__)
- Now ``BlockchainInterface.gas_strategy`` always has a value; previously it was possible to pass ``None`` via the constructor (e.g. if the config file had an explicit ``"null"`` value). (`#2421 <https://github.com/nucypher/nucypher/issues/2421>`__)
- Take advantage of the changes in PR#2410 by retrying worker commitments on failure (`#2422 <https://github.com/nucypher/nucypher/issues/2422>`__)
- Domain "leakage", or nodes saving metadata about nodes from other domains (but never being able to verify them) was still possible because domain-checking only occurred in the high-level APIs (and not, for example, when checking metadata POSTed to the node_metadata_exchange endpoint).  This fixes that (fixes #2417).

  Additionally, domains are no longer separated into "serving" or "learning".  Each Learner instance now has exactly one domain, and it is called domain. (`#2423 <https://github.com/nucypher/nucypher/issues/2423>`__)


Misc
~~~~

- Updates contract registry after upgrade of StakingEscrow to v5.5.1, at behest of the DAO (proposal #0). (`#2402 <https://github.com/nucypher/nucypher/issues/2402>`__)
- Improved newsfragments README file to clarify release note entry naming convention. (`#2415 <https://github.com/nucypher/nucypher/issues/2415>`__)


v4.1.1 (2020-10-29)
-------------------

Features
~~~~~~~~

- Add CLI functionality for the removal of unused (inactive) sub-stakes. Depending on the staker's sub-stake configuration, this command can reduce the associated worker's gas costs when making commitments. (`#2384 <https://github.com/nucypher/nucypher/issues/2384>`__)


Bugfixes
~~~~~~~~

- Automatically restart Ursula worker task on failure. (`#2410 <https://github.com/nucypher/nucypher/issues/2410>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Update global fee range documentation, including genesis values. (`#2363 <https://github.com/nucypher/nucypher/issues/2363>`__)


Misc
~~~~

- Update Ursula network grant availability script for mainnet usage. (`#2383 <https://github.com/nucypher/nucypher/issues/2383>`__)
- GitHub Action to ensure that each pull request into main makes an associated release note entry. (`#2396 <https://github.com/nucypher/nucypher/issues/2396>`__)


v4.1.0 (2020-10-19)
-------------------

Bugfixes
~~~~~~~~

- Temporary workaround for lack of single attribute for the value of "domain" in sprouts and mature nodes. (`#2356 <https://github.com/nucypher/nucypher/issues/2356>`__)
- Show the correct fleet state on Ursula status page. (`#2368 <https://github.com/nucypher/nucypher/issues/2368>`__)
- Don't crash when handling failed transaction; reduce network learning messages. (`#2375 <https://github.com/nucypher/nucypher/issues/2375>`__)
- Reduce the greediness of prometheus metrics collection. (`#2376 <https://github.com/nucypher/nucypher/issues/2376>`__)
- Ensure minimum NU stake is allowed instead of stake creation failing for not enough tokens. (`#2377 <https://github.com/nucypher/nucypher/issues/2377>`__)
- Fixes to status page based on reworked design done in PR #2351. (`#2378 <https://github.com/nucypher/nucypher/issues/2378>`__)
- Track pending Ursula commitment transactions due to slower gas strategies. (`#2389 <https://github.com/nucypher/nucypher/issues/2389>`__)


v4.0.1 (2020-10-14)
-------------------

Misc
~~~~

- Set default teacher uri for mainnet. (`#2367 <https://github.com/nucypher/nucypher/issues/2382>`__)


v4.0.0 (2020-10-14)
-------------------

**🚀 Mainnet Launch 🚀**
