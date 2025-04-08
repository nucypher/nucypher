========
Releases
========

.. towncrier release notes start

v7.5.0 (2025-04-08)
-------------------

Features
~~~~~~~~

- Support for executing multiple conditions sequentially, where the outcome of one condition can be used as input for another. (`#3500 <https://github.com/nucypher/nucypher/issues/3500>`__)
- Support for offchain JSON endpoint condition expression and evaluation (`#3511 <https://github.com/nucypher/nucypher/issues/3511>`__)
- Expands recovery CLI to include audit and keystore identification features (`#3538 <https://github.com/nucypher/nucypher/issues/3538>`__)
- Condition that allows for if-then-else branching based on underlying conditions i.e. IF ``CONDITION A`` THEN ``CONDITION B`` ELSE ``CONDITION_C``.
  The ELSE component can either be a Condition or a boolean value. (`#3558 <https://github.com/nucypher/nucypher/issues/3558>`__)
- Enable support for Bearer authorization tokens (e.g., OAuth, JWT) within HTTP GET requests for ``JsonApiCondition``. (`#3560 <https://github.com/nucypher/nucypher/issues/3560>`__)
- Enhance threshold decryption request efficiency by prioritizing nodes in the cohort with lower communication latency. (`#3562 <https://github.com/nucypher/nucypher/issues/3562>`__)
- Added plumbing to support EVM condition evaluation on "any" (major) EVM chain outside of Ethereum and Polygon - only enabled on ``lynx`` testnet for now. (`#3569 <https://github.com/nucypher/nucypher/issues/3569>`__)
- Support for conditions based on verification of JWT tokens. (`#3570 <https://github.com/nucypher/nucypher/issues/3570>`__)
- Support for conditions based on APIs provided by off-chain JSON RPC 2.0 endpoints. (`#3571 <https://github.com/nucypher/nucypher/issues/3571>`__)
- Add support for EIP1271 signature verification for smart contract wallets. (`#3576 <https://github.com/nucypher/nucypher/issues/3576>`__)
- Allow BigInt values from ``taco-web`` typescript library to be provided as strings. (`#3585 <https://github.com/nucypher/nucypher/issues/3585>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- `#3577 <https://github.com/nucypher/nucypher/issues/3577>`__


Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

- `#3523 <https://github.com/nucypher/nucypher/issues/3523>`__, `#3535 <https://github.com/nucypher/nucypher/issues/3535>`__, `#3539 <https://github.com/nucypher/nucypher/issues/3539>`__, `#3545 <https://github.com/nucypher/nucypher/issues/3545>`__, `#3547 <https://github.com/nucypher/nucypher/issues/3547>`__, `#3553 <https://github.com/nucypher/nucypher/issues/3553>`__, `#3554 <https://github.com/nucypher/nucypher/issues/3554>`__, `#3556 <https://github.com/nucypher/nucypher/issues/3556>`__, `#3557 <https://github.com/nucypher/nucypher/issues/3557>`__, `#3563 <https://github.com/nucypher/nucypher/issues/3563>`__, `#3564 <https://github.com/nucypher/nucypher/issues/3564>`__, `#3565 <https://github.com/nucypher/nucypher/issues/3565>`__, `#3578 <https://github.com/nucypher/nucypher/issues/3578>`__, `#3581 <https://github.com/nucypher/nucypher/issues/3581>`__, `#3586 <https://github.com/nucypher/nucypher/issues/3586>`__, `#3589 <https://github.com/nucypher/nucypher/issues/3589>`__
- Introduce necessary changes to adapt agents methods to breaking changes in Coordinator contract. Previous methods are now deprecated from the API. (`#3588 <https://github.com/nucypher/nucypher/issues/3588>`__)


v7.4.1 (2024-09-12)
-------------------

Bugfixes
~~~~~~~~

- Prevent connectivity issues from improperly re-initializing underlying instances of ``EthereumClient``
  and ``Web3`` within a ``BlockchainInterface`` instance. (`#3549 <https://github.com/nucypher/nucypher/issues/3549>`__)


v7.4.0 (2024-08-12)
-------------------

Features
~~~~~~~~

- Support for default/fallback RPC endpoints from remote sources as a backup for operator-supplied RPC endpoints for condition evaluation. (`#3496 <https://github.com/nucypher/nucypher/issues/3496>`__)
- Add support for Sign-in With Ethereum (SIWE) messages to be used when verifying wallet address ownership for the ``:userAddress`` special context variable during decryption requests. (`#3502 <https://github.com/nucypher/nucypher/issues/3502>`__)
- Add functionality for ``:userAddressEIP712`` and ``:userAddressEIP4361`` to provide specific authentication
  support for user address context values for conditions. ``:userAddress`` will allow any valid authentication scheme. (`#3508 <https://github.com/nucypher/nucypher/issues/3508>`__)
- Add ability for special context variable to handle Sign-In With Ethereum (EIP-4361)
  pre-existing sign-on signature to be reused as proof for validating a user address in conditions. (`#3513 <https://github.com/nucypher/nucypher/issues/3513>`__)
- Prevents nodes from starting up or participating in DKGs if there is a local vs. onchain ferveo key mismatch.  This will assist in alerting node operators who need to relocate or recover their hosts about the correct procedure. (`#3529 <https://github.com/nucypher/nucypher/issues/3529>`__)
- Prevent new nodes from initialization if the operator already has published a ferveo public key onchain.
  Improves information density and communication of keystore security obligations while using the init CLI. (`#3533 <https://github.com/nucypher/nucypher/issues/3533>`__)


Bugfixes
~~~~~~~~

- Do not continuously retry ritual actions when unrecoverable ferveo error occurs during ritual ceremony. (`#3524 <https://github.com/nucypher/nucypher/issues/3524>`__)
- ATxM instance did not pass correct web3 instance to underlying strategies. (`#3531 <https://github.com/nucypher/nucypher/issues/3531>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Drop support for Python 3.8. (`#3521 <https://github.com/nucypher/nucypher/issues/3521>`__)


Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

- `#3446 <https://github.com/nucypher/nucypher/issues/3446>`__, `#3498 <https://github.com/nucypher/nucypher/issues/3498>`__, `#3499 <https://github.com/nucypher/nucypher/issues/3499>`__, `#3507 <https://github.com/nucypher/nucypher/issues/3507>`__, `#3509 <https://github.com/nucypher/nucypher/issues/3509>`__, `#3510 <https://github.com/nucypher/nucypher/issues/3510>`__, `#3519 <https://github.com/nucypher/nucypher/issues/3519>`__, `#3521 <https://github.com/nucypher/nucypher/issues/3521>`__, `#3522 <https://github.com/nucypher/nucypher/issues/3522>`__, `#3532 <https://github.com/nucypher/nucypher/issues/3532>`__


v7.3.0 (2024-05-07)
-------------------

Features
~~~~~~~~

- Automated transaction speedups and retries (`#3437 <https://github.com/nucypher/nucypher/issues/3437>`__)
- Allow staking providers to be filtered/sampled based on an expectation for staking duration. (`#3467 <https://github.com/nucypher/nucypher/issues/3467>`__)
- Improve DKG transaction fault tolerance by incorporating async transactions and callbacks. (`#3476 <https://github.com/nucypher/nucypher/issues/3476>`__)
- Add ``--json-logs/--no-json-logs`` CLI option to enabled/disable logging to a json log file; json logging is now disabled be default. (`#3483 <https://github.com/nucypher/nucypher/issues/3483>`__)
- RPC connectivity is now agnostic to the EVM client fingerprint and implementation technology. (`#3491 <https://github.com/nucypher/nucypher/issues/3491>`__)


Bugfixes
~~~~~~~~

- Migrate configuration files when path explicitly specified as a CLI parameter. (`#3465 <https://github.com/nucypher/nucypher/issues/3465>`__)
- Add --metrics-listen-address CLI Prometheus option (`#3478 <https://github.com/nucypher/nucypher/issues/3478>`__)
- Console logging was not using the correct log format, log levels were not adhered to for limiting log messages, and global log observers not correctly managed.
  Improved the StdoutEmitter to better utilize the logger so that information is not lost. (`#3483 <https://github.com/nucypher/nucypher/issues/3483>`__)
- Fix inconsistent API for ``sign_transaction`` return values; all now return bytes. (`#3486 <https://github.com/nucypher/nucypher/issues/3486>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Wallet management and transaction signing via blockchain clients is deprecated for production use. (`#3491 <https://github.com/nucypher/nucypher/issues/3491>`__)


Misc
~~~~

- Migrate ``Lynx`` and ``Tapir`` testnets from Polygon Mumbai to Polygon Amoy. (`#3468 <https://github.com/nucypher/nucypher/issues/3468>`__)
- Nodes will better handle the effects of compatible contract changes such as additions to structs and overloaded functions. (`#3479 <https://github.com/nucypher/nucypher/issues/3479>`__)
- Ensure that log observers filter log messages by log level. (`#3487 <https://github.com/nucypher/nucypher/issues/3487>`__)
- Prevent ritual tx starvation when broadcast failures occur by proactively removing problematic tx from the ATxM queue, and resubmitting a fresh tx. (`#3489 <https://github.com/nucypher/nucypher/issues/3489>`__)


Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#3409 <https://github.com/nucypher/nucypher/issues/3409>`__, `#3438 <https://github.com/nucypher/nucypher/issues/3438>`__, `#3439 <https://github.com/nucypher/nucypher/issues/3439>`__, `#3457 <https://github.com/nucypher/nucypher/issues/3457>`__, `#3462 <https://github.com/nucypher/nucypher/issues/3462>`__, `#3464 <https://github.com/nucypher/nucypher/issues/3464>`__, `#3473 <https://github.com/nucypher/nucypher/issues/3473>`__, `#3477 <https://github.com/nucypher/nucypher/issues/3477>`__, `#3484 <https://github.com/nucypher/nucypher/issues/3484>`__)


v7.2.0 (2024-02-13)
-------------------

Features
~~~~~~~~

- Automatically migrate configuration files if detected as using an older version. (`#3432 <https://github.com/nucypher/nucypher/issues/3432>`__)
- Add workflow for pushing published releases to pypi (`#3433 <https://github.com/nucypher/nucypher/issues/3433>`__)


Bugfixes
~~~~~~~~

- Incorrect use of ``INTERVAL`` class variable for ``SimpleTask`` - it affected the interval for the ``EventScannerTask``. (`#3435 <https://github.com/nucypher/nucypher/issues/3435>`__)
- Properly update ssl contexts to use updated CA cert data for a node which has been restarted. (`#3440 <https://github.com/nucypher/nucypher/issues/3440>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removes the /node_metadata GET endpoint (`#3410 <https://github.com/nucypher/nucypher/issues/3410>`__)


Misc
~~~~

- Peer TLS certificates are no longer stored on the node's disk. (`#3307 <https://github.com/nucypher/nucypher/issues/3307>`__)
- Optimizes blockchain reads for dkg coordination and artifacts for call data volume. (`#3419 <https://github.com/nucypher/nucypher/issues/3419>`__)
- Improve caching of data needed for threshold decryption by the node - reduces RPC calls and decryption time. (`#3428 <https://github.com/nucypher/nucypher/issues/3428>`__)
- Optimize EventScanner chunking for Polygon given its blocktime. (`#3434 <https://github.com/nucypher/nucypher/issues/3434>`__)
- Update EventScanner to obtain events of different types as part of the same RPC
  call to reduce the volume of rpc calls. (`#3444 <https://github.com/nucypher/nucypher/issues/3444>`__)


Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#3387 <https://github.com/nucypher/nucypher/issues/3387>`__, `#3414 <https://github.com/nucypher/nucypher/issues/3414>`__, `#3420 <https://github.com/nucypher/nucypher/issues/3420>`__, `#3445 <https://github.com/nucypher/nucypher/issues/3445>`__)
- Reintroduce ``simple_cache_middleware`` to cache some RPC calls like ``eth_chainId``. (`#3436 <https://github.com/nucypher/nucypher/issues/3436>`__)


v7.1.0 (2024-01-30)
-------------------

Features
~~~~~~~~

- Make Prometheus exporter always run for Ursula (`#3223 <https://github.com/nucypher/nucypher/issues/3223>`__)
-  (`#3224 <https://github.com/nucypher/nucypher/issues/3224>`__)
- Add Prometheus metrics endpoint to running logs (`#3231 <https://github.com/nucypher/nucypher/issues/3231>`__)
- Add metrics for root and child networks. (`#3339 <https://github.com/nucypher/nucypher/issues/3339>`__)
- Make prometheus optional, and allow fine tuning of collection interval. (`#3388 <https://github.com/nucypher/nucypher/issues/3388>`__)
- Add prometheus metrics for tracking total threshold decryption requests and errors. (`#3397 <https://github.com/nucypher/nucypher/issues/3397>`__)


Bugfixes
~~~~~~~~

- Don't use web3.py gas strategies, since that switches TX mode to legacy. (`#3368 <https://github.com/nucypher/nucypher/issues/3368>`__)
- Node blocks and remains unresponsive when another node in the cohort is
  unreachable during a dkg ritual because the ferveo public key is obtained from
  a node directly through node discovery. Instead, obtain ferveo public key
  from Coordinator contract so that connecting to the another node in
  the cohort is unnecessary. (`#3390 <https://github.com/nucypher/nucypher/issues/3390>`__)
- Fix `MAX_UPLOAD_CONTENT_LENGTH` too small for mainnet TACo rituals (`#3396 <https://github.com/nucypher/nucypher/issues/3396>`__)
- Ensure incoming request ip addresses resolution handles proxied headers. (`#3398 <https://github.com/nucypher/nucypher/issues/3398>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#3232 <https://github.com/nucypher/nucypher/issues/3232>`__)


Misc
~~~~

- Peer TLS certificates are no longer stored on the node's disk. (`#3307 <https://github.com/nucypher/nucypher/issues/3307>`__)
- Deprecate use of Goerli for Lynx testnets; use Sepolia instead. (`#3376 <https://github.com/nucypher/nucypher/issues/3376>`__)
- Scan for ritual events less often to be more efficient with RPC requests. (`#3416 <https://github.com/nucypher/nucypher/issues/3416>`__)


Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#3245 <https://github.com/nucypher/nucypher/issues/3245>`__, `#3310 <https://github.com/nucypher/nucypher/issues/3310>`__, `#3327 <https://github.com/nucypher/nucypher/issues/3327>`__, `#3333 <https://github.com/nucypher/nucypher/issues/3333>`__, `#3361 <https://github.com/nucypher/nucypher/issues/3361>`__, `#3386 <https://github.com/nucypher/nucypher/issues/3386>`__, `#3387 <https://github.com/nucypher/nucypher/issues/3387>`__, `#3405 <https://github.com/nucypher/nucypher/issues/3405>`__, `#3406 <https://github.com/nucypher/nucypher/issues/3406>`__, `#3408 <https://github.com/nucypher/nucypher/issues/3408>`__)
- Optimize use of decryption request WorkerPool. (`#3393 <https://github.com/nucypher/nucypher/issues/3393>`__)


v7.0.4 (2023-12-15)
-------------------

Bugfixes
~~~~~~~~

- Don't needlessly block during ``block_until_ready`` on node startup if node is deemed to be bonded and funded. (`#3366 <https://github.com/nucypher/nucypher/issues/3366>`__)


v7.0.3 (2023-12-11)
-------------------

Misc
~~~~

- Increase startup poll rate for checking bonding/funding from 10s to 120s. (`#3364 <https://github.com/nucypher/nucypher/issues/3364>`__)


v7.0.2 (2023-12-07)
-------------------


v7.0.1 (2023-12-04)
-------------------

Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#3360 <https://github.com/nucypher/nucypher/issues/3360>`__)


v7.0.0 (2023-12-01)
-------------------

Features
~~~~~~~~

- Basic support for polygon conditions (`#2986 <https://github.com/nucypher/nucypher/issues/2986>`__)
- Add artifacts for new network: tapir (`#2996 <https://github.com/nucypher/nucypher/issues/2996>`__)
- Update contract registry for lynx network (`#3000 <https://github.com/nucypher/nucypher/issues/3000>`__)
- Allow a key to be specified for evaluating the return value (`#3002 <https://github.com/nucypher/nucypher/issues/3002>`__)
- Bump ``nucypher-core`` to 0.6. (`#3049 <https://github.com/nucypher/nucypher/issues/3049>`__)
- Include inventory entries for oryx. (`#3069 <https://github.com/nucypher/nucypher/issues/3069>`__)
- Introduces support for DKG and Threshold Decryption. (`#3083 <https://github.com/nucypher/nucypher/issues/3083>`__)
- Enables "Simple" threshold decryption variant and threshold decryption functionlity by Bob. (`#3088 <https://github.com/nucypher/nucypher/issues/3088>`__)
- End-to-end encryption for CBD decryption requests. (`#3123 <https://github.com/nucypher/nucypher/issues/3123>`__)
- ``TimeCondition`` now uses the timestamp of the latest block for evaluating conditions, instead of system time. System time condition evaluation is no longer supported. (`#3139 <https://github.com/nucypher/nucypher/issues/3139>`__)
- Implement prefix notation for access control conditions with logical operators. (`#3140 <https://github.com/nucypher/nucypher/issues/3140>`__)
- Sublcasses of Bob and Enrico which allow local, off-chain development and styling of both success and failure cases, which can be forced instead of checking conditions. (`#3143 <https://github.com/nucypher/nucypher/issues/3143>`__)
- Add version element to condition language to allow future changes and to manage backwards compatibility. (`#3145 <https://github.com/nucypher/nucypher/issues/3145>`__)
- Increase default timeout for ``/reencrypt`` requests to limit timeouts when multiple retrieval kits are included in a single request. (`#3153 <https://github.com/nucypher/nucypher/issues/3153>`__)
- Reset default ferveo variant to be ``simple``. We can revisit whenever we add logic to properly deal with request failures for the ``precomputed`` variant. (`#3174 <https://github.com/nucypher/nucypher/issues/3174>`__)
- - Support arbitrary multichain configuration for EVM-compatible blockchains for condition evaluation by ursula.
  - Support for fallback RPC providers and multiple URI specification for a single chain ID. (`#3185 <https://github.com/nucypher/nucypher/issues/3185>`__)
- Implement data encapsulation when encrypting data using ``ferveo`` encryption by utilizing ``ThresholdMessageKit`` and ``AccessControlPolicy``.
  Provide framework to incorporate authorization allow logic for authorized encryptors of data for a ritual. (`#3194 <https://github.com/nucypher/nucypher/issues/3194>`__)
- Add a mandatory condition_type field to condition schemas (`#3201 <https://github.com/nucypher/nucypher/issues/3201>`__)
- New HTTP(S) endpoint to return a list of all the blockchains a node is currently connected to for conditions evaluation. (`#3205 <https://github.com/nucypher/nucypher/issues/3205>`__)
- Introduces `nucypher ursula config migrate` for configuration file automation. (`#3207 <https://github.com/nucypher/nucypher/issues/3207>`__)
- Implement functionality related to Encryptor authorization for specific ritual.
  Obtain ritual threshold from Coordinator contract. (`#3213 <https://github.com/nucypher/nucypher/issues/3213>`__)
- Nodes reject decryption requests for already expired rituals. (`#3279 <https://github.com/nucypher/nucypher/issues/3279>`__)
- Added ``not`` operator functionality to ``CompoundAccessControlCondition`` so that the logical inverse of conditions can be evaluated. (`#3293 <https://github.com/nucypher/nucypher/issues/3293>`__)
- Allow Bob / ThresholdAccessControlClient decryption and reencryption operations to specify timeouts. (`#3337 <https://github.com/nucypher/nucypher/issues/3337>`__)
- Use ``TACoChildApplication`` contract for node sampling instead of ``TACoApplication`` contract. (`#3341 <https://github.com/nucypher/nucypher/issues/3341>`__)


Bugfixes
~~~~~~~~

- temp workaround for Ropsten/oryx gas estimation issue (`#2943 <https://github.com/nucypher/nucypher/issues/2943>`__)
- Show fleet state checksums as hex instead of an escaped bytestring (`#2946 <https://github.com/nucypher/nucypher/issues/2946>`__)
- Correctly validate domain/network values provided via the ``--network`` parameter in the CLI. (`#2952 <https://github.com/nucypher/nucypher/issues/2952>`__)
- Call `_resolve_abi` after the condition is initialized (`#3014 <https://github.com/nucypher/nucypher/issues/3014>`__)
- Properly handle PRE request with no condition. (`#3025 <https://github.com/nucypher/nucypher/issues/3025>`__)
- Restrict return value `key` to integer only (`#3032 <https://github.com/nucypher/nucypher/issues/3032>`__)
- Use decoded text from failed HTTP Responses for exception messages. (`#3042 <https://github.com/nucypher/nucypher/issues/3042>`__)
- Properly convert ritual id to bytes when being used as a seed for generating a session key. (`#3178 <https://github.com/nucypher/nucypher/issues/3178>`__)
- Fix staking metrics in Prometheus exporter (`#3199 <https://github.com/nucypher/nucypher/issues/3199>`__)
- Fix Prometheus import error when running Porter (`#3202 <https://github.com/nucypher/nucypher/issues/3202>`__)
-  (`#3203 <https://github.com/nucypher/nucypher/issues/3203>`__, `#3209 <https://github.com/nucypher/nucypher/issues/3209>`__, `#3214 <https://github.com/nucypher/nucypher/issues/3214>`__)
- ``UrsulaConfiguration`` object should not be too eager to connect to provided blockchain endpoints; if faulty then the configuration file can't be updated. (`#3282 <https://github.com/nucypher/nucypher/issues/3282>`__)
- Fix nucypher CLI: ``ursula config ip-address`` (`#3292 <https://github.com/nucypher/nucypher/issues/3292>`__)
- Fix issues when bytes are provided as hex for return value comparators.
  Make condition value types more strict by using ABI to validate. (`#3303 <https://github.com/nucypher/nucypher/issues/3303>`__)
- Address bug where context variable not properly processed when doing type checking for multi-value output. (`#3312 <https://github.com/nucypher/nucypher/issues/3312>`__)
- Include the port in ``seeds.nucyher.network`` URL entry in dictionary of teacher nodes for mainnet. (`#3332 <https://github.com/nucypher/nucypher/issues/3332>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Add recommendation/information about restart functionality when running a PRE node. (`#2945 <https://github.com/nucypher/nucypher/issues/2945>`__)
- Relocates documentation to https://docs.threshold.network (https://github.com/threshold-network/threshold). (`#3311 <https://github.com/nucypher/nucypher/issues/3311>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Remove set up dependency on ``setuptools-markdown`` which is no longer needed, but caused build failures. (`#2942 <https://github.com/nucypher/nucypher/issues/2942>`__)
- Deprecates alice, bob, and contact CLI commands. (`#2985 <https://github.com/nucypher/nucypher/issues/2985>`__)
- Removals: 
  - RPC servers
  - character WebControllers
  - unused literature
  - unused CLI option definitions
  - CLI helper functions for Alice, Bob, Contacts interactivity
  - interactive Ursula mode
  - enrico CLI commands (`#2987 <https://github.com/nucypher/nucypher/issues/2987>`__)
- Removes LMDB Datastore (`#2988 <https://github.com/nucypher/nucypher/issues/2988>`__)
- Removes clef and trezor signer support (`#2989 <https://github.com/nucypher/nucypher/issues/2989>`__)
- Relocate porter to nucypher/nucypher-porter (`#2990 <https://github.com/nucypher/nucypher/issues/2990>`__)
- Retires the Ibex and Oryx testnets (`#2998 <https://github.com/nucypher/nucypher/issues/2998>`__)
- Deprecated "federated mode" ursulas and the --federated-only launch flag. (`#3030 <https://github.com/nucypher/nucypher/issues/3030>`__)
- Deprecated "timelock" time condition that used system time in favor of a condition that uses block time. (`#3139 <https://github.com/nucypher/nucypher/issues/3139>`__)
- Remove the use of infix notation for access control conditions with logical operators in favor of prefix notation. (`#3140 <https://github.com/nucypher/nucypher/issues/3140>`__)
- removes `nucypher bond` CLI (`#3149 <https://github.com/nucypher/nucypher/issues/3149>`__)
-  (`#3234 <https://github.com/nucypher/nucypher/issues/3234>`__)
- Remove ``EconomicsFactory`` and ``Economics`` classes. (`#3241 <https://github.com/nucypher/nucypher/issues/3241>`__)
- Remove ``AdjudicatorAgent`` and custom ``Dispatcher`` proxy logic. (`#3243 <https://github.com/nucypher/nucypher/issues/3243>`__)
- Deprecate configuration config/parameters ``pre-payment-network``, ``coordinator_uri`` since the L2 network is implied based on TACo network used. (`#3262 <https://github.com/nucypher/nucypher/issues/3262>`__)


Misc
~~~~

- Add default seed node for Oryx testnet. (`#2944 <https://github.com/nucypher/nucypher/issues/2944>`__)
- Prometheus metrics exporter returned (`#2950 <https://github.com/nucypher/nucypher/issues/2950>`__)
- Extends policy probationary period until August 31st, 2022. No policies may be created on the network beyond this date. (`#2952 <https://github.com/nucypher/nucypher/issues/2952>`__)
- Cleanup of prometheus metrics collection. (`#2954 <https://github.com/nucypher/nucypher/issues/2954>`__)
- Reworks internal blockchain connection cache to support multiple concurrent connections. (`#3137 <https://github.com/nucypher/nucypher/issues/3137>`__)
- Ensure that nodes can be more resilient when handling events related to rituals. (`#3183 <https://github.com/nucypher/nucypher/issues/3183>`__)
- Use a time-to-live cache for trakcing ritual participation state which gets periodically purged when ritual state is deemed stale. (`#3191 <https://github.com/nucypher/nucypher/issues/3191>`__)
- Don't allow users to specify the FerveoVariant to use for threshold decryption. The default, simple variant, will be used. (`#3193 <https://github.com/nucypher/nucypher/issues/3193>`__)
-  (`#3204 <https://github.com/nucypher/nucypher/issues/3204>`__, `#3210 <https://github.com/nucypher/nucypher/issues/3210>`__, `#3215 <https://github.com/nucypher/nucypher/issues/3215>`__, `#3220 <https://github.com/nucypher/nucypher/issues/3220>`__)
- Update Ursula configuration version from 6 to 7.
  Check operator for MATIC funding instead of ETH on startup.
  Handle separation between mainnet root application contract and l2 child application contract. (`#3227 <https://github.com/nucypher/nucypher/issues/3227>`__)
- Properly detect operator bonding status by using both ``TACoChildApplicationAgent`` and ``TACoApplicationAgent`` to ensure consistency. (`#3237 <https://github.com/nucypher/nucypher/issues/3237>`__)
- Contract registries now use JSON format and support multi-chain deployments organized by nucypher "domain". (`#3261 <https://github.com/nucypher/nucypher/issues/3261>`__)
- Since the L2 network is always implied based on the TACo network connected to, we no longer need those config/parameters across the codebase, it can be inferred.
  Each Character now takes optional eth and polygon endpoints.
  Remove various usages of redundant L2 values. General rename from ``[eth_]provider[_uri]`` to ``[blockchain/eth/polygon]_endpoint``. (`#3262 <https://github.com/nucypher/nucypher/issues/3262>`__)
- Add ``tapir`` contract registry. (`#3277 <https://github.com/nucypher/nucypher/issues/3277>`__)
- Reduce the number of times the blockchain is queried for chain id. (`#3285 <https://github.com/nucypher/nucypher/issues/3285>`__)
- Add ``nucypher taco rituals`` CLI command to list ritual information for a TACo domain. (`#3290 <https://github.com/nucypher/nucypher/issues/3290>`__)
- Require condition RPC endpoints for node startup (`#3318 <https://github.com/nucypher/nucypher/issues/3318>`__)


Internal Development Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#3019 <https://github.com/nucypher/nucypher/issues/3019>`__, `#3021 <https://github.com/nucypher/nucypher/issues/3021>`__, `#3022 <https://github.com/nucypher/nucypher/issues/3022>`__, `#3023 <https://github.com/nucypher/nucypher/issues/3023>`__, `#3024 <https://github.com/nucypher/nucypher/issues/3024>`__, `#3026 <https://github.com/nucypher/nucypher/issues/3026>`__, `#3028 <https://github.com/nucypher/nucypher/issues/3028>`__, `#3029 <https://github.com/nucypher/nucypher/issues/3029>`__, `#3034 <https://github.com/nucypher/nucypher/issues/3034>`__, `#3037 <https://github.com/nucypher/nucypher/issues/3037>`__, `#3040 <https://github.com/nucypher/nucypher/issues/3040>`__, `#3046 <https://github.com/nucypher/nucypher/issues/3046>`__, `#3048 <https://github.com/nucypher/nucypher/issues/3048>`__, `#3071 <https://github.com/nucypher/nucypher/issues/3071>`__, `#3126 <https://github.com/nucypher/nucypher/issues/3126>`__, `#3134 <https://github.com/nucypher/nucypher/issues/3134>`__, `#3135 <https://github.com/nucypher/nucypher/issues/3135>`__, `#3138 <https://github.com/nucypher/nucypher/issues/3138>`__, `#3152 <https://github.com/nucypher/nucypher/issues/3152>`__, `#3158 <https://github.com/nucypher/nucypher/issues/3158>`__, `#3159 <https://github.com/nucypher/nucypher/issues/3159>`__, `#3160 <https://github.com/nucypher/nucypher/issues/3160>`__, `#3162 <https://github.com/nucypher/nucypher/issues/3162>`__, `#3165 <https://github.com/nucypher/nucypher/issues/3165>`__, `#3169 <https://github.com/nucypher/nucypher/issues/3169>`__, `#3170 <https://github.com/nucypher/nucypher/issues/3170>`__, `#3171 <https://github.com/nucypher/nucypher/issues/3171>`__, `#3179 <https://github.com/nucypher/nucypher/issues/3179>`__, `#3196 <https://github.com/nucypher/nucypher/issues/3196>`__, `#3208 <https://github.com/nucypher/nucypher/issues/3208>`__, `#3216 <https://github.com/nucypher/nucypher/issues/3216>`__, `#3221 <https://github.com/nucypher/nucypher/issues/3221>`__, `#3222 <https://github.com/nucypher/nucypher/issues/3222>`__, `#3233 <https://github.com/nucypher/nucypher/issues/3233>`__, `#3238 <https://github.com/nucypher/nucypher/issues/3238>`__, `#3239 <https://github.com/nucypher/nucypher/issues/3239>`__, `#3250 <https://github.com/nucypher/nucypher/issues/3250>`__, `#3252 <https://github.com/nucypher/nucypher/issues/3252>`__, `#3254 <https://github.com/nucypher/nucypher/issues/3254>`__, `#3255 <https://github.com/nucypher/nucypher/issues/3255>`__, `#3256 <https://github.com/nucypher/nucypher/issues/3256>`__, `#3257 <https://github.com/nucypher/nucypher/issues/3257>`__, `#3258 <https://github.com/nucypher/nucypher/issues/3258>`__, `#3267 <https://github.com/nucypher/nucypher/issues/3267>`__, `#3271 <https://github.com/nucypher/nucypher/issues/3271>`__, `#3272 <https://github.com/nucypher/nucypher/issues/3272>`__, `#3274 <https://github.com/nucypher/nucypher/issues/3274>`__, `#3275 <https://github.com/nucypher/nucypher/issues/3275>`__, `#3276 <https://github.com/nucypher/nucypher/issues/3276>`__, `#3295 <https://github.com/nucypher/nucypher/issues/3295>`__, `#3298 <https://github.com/nucypher/nucypher/issues/3298>`__, `#3304 <https://github.com/nucypher/nucypher/issues/3304>`__, `#3306 <https://github.com/nucypher/nucypher/issues/3306>`__, `#3308 <https://github.com/nucypher/nucypher/issues/3308>`__, `#3309 <https://github.com/nucypher/nucypher/issues/3309>`__, `#3312 <https://github.com/nucypher/nucypher/issues/3312>`__, `#3315 <https://github.com/nucypher/nucypher/issues/3315>`__, `#3317 <https://github.com/nucypher/nucypher/issues/3317>`__, `#3321 <https://github.com/nucypher/nucypher/issues/3321>`__, `#3323 <https://github.com/nucypher/nucypher/issues/3323>`__, `#3325 <https://github.com/nucypher/nucypher/issues/3325>`__, `#3330 <https://github.com/nucypher/nucypher/issues/3330>`__, `#3334 <https://github.com/nucypher/nucypher/issues/3334>`__, `#3335 <https://github.com/nucypher/nucypher/issues/3335>`__, `#3338 <https://github.com/nucypher/nucypher/issues/3338>`__, `#3344 <https://github.com/nucypher/nucypher/issues/3344>`__, `#3345 <https://github.com/nucypher/nucypher/issues/3345>`__, `#3347 <https://github.com/nucypher/nucypher/issues/3347>`__, `#3348 <https://github.com/nucypher/nucypher/issues/3348>`__)
- Updates to use ferveo v0.1.11. (`#3121 <https://github.com/nucypher/nucypher/issues/3121>`__)
- Add profiling option to ``testnet_simple_taco.py`` demo. (`#3284 <https://github.com/nucypher/nucypher/issues/3284>`__)
- Context variable names are restricted to alphanumeric characters, numbers and underscores. (`#3331 <https://github.com/nucypher/nucypher/issues/3331>`__)


v6.1.0 (2022-05-10)
-------------------

Features
~~~~~~~~

- SSL Certificate fetching and Porter optimizations
  - Middleware should try cached SSL certification for a node first, and then if the requests fails, fetch the node's up-to-date SSL cert
  - Short-circuit WorkerPool background execution once sufficient successful executions occur
  - Don't limit WorkerPool size; this has consequences when smaller samples of ursulas are performed; allow threadpool to be flexible by using default min/max
  - Return more comprehensive error information for failed WorkerPool execution (`#2908 <https://github.com/nucypher/nucypher/issues/2908>`__)


Bugfixes
~~~~~~~~

- Fix Porter sampling check that ensures Ursula is reachable to be more comprehensive; previously an unreachable Ursula could still be deemed as reachable. (`#2888 <https://github.com/nucypher/nucypher/issues/2888>`__)
- Only print relevant network options when running `nucypher ursula init` (`#2917 <https://github.com/nucypher/nucypher/issues/2917>`__)
- Retrieve contract registries from the ``development`` branch on GitHub instead of ``main``. (`#2924 <https://github.com/nucypher/nucypher/issues/2924>`__)
- Properly support event retrieval for the PREApplication contract.
  Remove invalid support for SubscriptionManager contract - proper support will be
  added in a future release. (`#2934 <https://github.com/nucypher/nucypher/issues/2934>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Remove references to ``cloudworkers`` CLI command, and update bond operator to reference UI. (`#2896 <https://github.com/nucypher/nucypher/issues/2896>`__)
- Updated examples and demos for usage on polygon/mainnet. (`#2897 <https://github.com/nucypher/nucypher/issues/2897>`__)
- Updates to nucypher-ops guides for mainnet usage (`#2916 <https://github.com/nucypher/nucypher/issues/2916>`__)


Misc
~~~~

- Dependency updates - Tests target the london fork. (`#2837 <https://github.com/nucypher/nucypher/issues/2837>`__)
- Creation of 'oryx' PRE testnet on Ropsten. (`#2893 <https://github.com/nucypher/nucypher/issues/2893>`__)
- Add more color to cli output (`#2909 <https://github.com/nucypher/nucypher/issues/2909>`__)
- Add a pre-commit hook and github action for `Darker <https://github.com/akaihola/darker>`_ to ensure all future changes conform to black and isort. (`#2921 <https://github.com/nucypher/nucypher/issues/2921>`__)
- Bump ``nucypher-core`` dependency to 0.2 (`#2927 <https://github.com/nucypher/nucypher/issues/2927>`__)
- Show error message when ``--prometheus`` flag is used since functionality not currently supported. Prometheus
  monitoring functionality will be revamped in a subsequent release. (`#2929 <https://github.com/nucypher/nucypher/issues/2929>`__)
- Removes [docs] pip extra (`#2932 <https://github.com/nucypher/nucypher/issues/2932>`__)


v6.0.0 (2022-04-01)
-------------------

Features
~~~~~~~~

- Introduction of NuCypher Porter - a web-based service that performs ``nucypher`` protocol operations on behalf of applications for cross-platform functionality. (`#2664 <https://github.com/nucypher/nucypher/issues/2664>`__)
- Ursula no longer stores KFrags, instead Alice encrypts them inside the treasure map.  Allow the KFrag generator and policy publisher to be different entities. (`#2687 <https://github.com/nucypher/nucypher/issues/2687>`__)
- Characters use mnemonic seed words to derive deterministic keystore, taking the place of the "keyring". (`#2701 <https://github.com/nucypher/nucypher/issues/2701>`__)
- Simplifies the retrieval protocol (see `#259 <https://github.com/nucypher/nucypher/issues/259>`_ for the discussion). ``PolicyMessageKit`` is renamed to ``MessageKit``. ``Bob.retrieve()`` is renamed to ``retrieve_and_decrypt()``, and its signature is simplified: it only requires the treasure map, Alice's verifying key, and the policy encrypting key. A lower-level ``Bob.retrieve()`` is added that does not decrypt, but only attempts to retrieve the capsule frags. (`#2730 <https://github.com/nucypher/nucypher/issues/2730>`__)
- Allow importing of secret key material for power derivations. (`#2742 <https://github.com/nucypher/nucypher/issues/2742>`__)
- Uniform versioning of bytes serializable protocol entities. (`#2767 <https://github.com/nucypher/nucypher/issues/2767>`__)
- Modify Porter REST endpoint from ``/exec_work_order`` to ``/retrieve_cfrags`` and modify request parameters for retrieval of re-encrypted data.
  Update Bob ``/retrieve_and_decrypt`` REST endpoint to accept a list of message kits instead of only one - to match updated ``Bob.retrieve_and_decrypt`` Python API. (`#2768 <https://github.com/nucypher/nucypher/issues/2768>`__)
- Update WorkerPool error messages returned by Porter API. (`#2772 <https://github.com/nucypher/nucypher/issues/2772>`__)
- Adds ansible build/deploy for Monitor (status.nucypher.network) (`#2801 <https://github.com/nucypher/nucypher/issues/2801>`__)
- Extend brand size in ``Versioned`` to 4 bytes (`#2805 <https://github.com/nucypher/nucypher/issues/2805>`__)
- CORS, NGINX support for Porter:
  - Added opt-in CORS origins support to Porter; no origins allowed by default when running Porter directly.
  - Provided docker-compose execution for Porter to run behind an NGINX reverse proxy server - all origins allowed by default for CORS, but can be customized. NGINX allows for the potential for more complex infrastructure configurations. (`#2807 <https://github.com/nucypher/nucypher/issues/2807>`__)
-  (`#2809 <https://github.com/nucypher/nucypher/issues/2809>`__)
- Halting NU inflation, now refund in WorkLock is possible without work (claim still needed) (`#2822 <https://github.com/nucypher/nucypher/issues/2822>`__)
- Updates to integrate NuCypher into Threshold Network (`#2824 <https://github.com/nucypher/nucypher/issues/2824>`__)
- Integrate StakingEscrow with Threshold Network's TokenStaking (`#2825 <https://github.com/nucypher/nucypher/issues/2825>`__)
- Removes snapshots logic from ``StakingEscrow`` (`#2831 <https://github.com/nucypher/nucypher/issues/2831>`__)
- Switched to Rust implementation of the protocol types (``nucypher-core``). Correspondingly, API has been simplified, and type requirements have been made more strict. (`#2832 <https://github.com/nucypher/nucypher/issues/2832>`__)
- Simple PRE application contract (`#2838 <https://github.com/nucypher/nucypher/issues/2838>`__)
- Renames operator to staking provider and worker to operator (`#2851 <https://github.com/nucypher/nucypher/issues/2851>`__)
- Modifies Ursulas for usage as Operators on the Threshold Network's PRE Application. (`#2857 <https://github.com/nucypher/nucypher/issues/2857>`__)
- - Full support of policy payments sumitted to polygon in demos and top-level APIs.
  - Improved certificate handling for network requests.
  - Prioritizes in-memory node storage for all node runtimes. (`#2873 <https://github.com/nucypher/nucypher/issues/2873>`__)
- Updated nucypher-core to 0.1 (`#2883 <https://github.com/nucypher/nucypher/issues/2883>`__)
- Proactively shut down Ursula if it is no longer bonded to any staking provider. (`#2886 <https://github.com/nucypher/nucypher/issues/2886>`__)
- Include polygon/matic contract registry for mainnet. (`#2894 <https://github.com/nucypher/nucypher/issues/2894>`__)


Bugfixes
~~~~~~~~

-  (`#2727 <https://github.com/nucypher/nucypher/issues/2727>`__)
- Cloudworkers: ignore errors on stopping of ursula containers (`#2728 <https://github.com/nucypher/nucypher/issues/2728>`__)
- Fixed a problem with node metadata being stored to a file with an incorrect name (`#2748 <https://github.com/nucypher/nucypher/issues/2748>`__)
- Fixed failing transactions when gas price used is not an integer. (`#2753 <https://github.com/nucypher/nucypher/issues/2753>`__)
- Stop writing bytes to log file which causes exceptions - instead write the hex representation. (`#2762 <https://github.com/nucypher/nucypher/issues/2762>`__)
- ``StakingEscrow.partition_stakers_by_activity()`` no longer includes stakers with expired stakes in the ``missing_stakers`` value returned, thereby no longer overstating the number of inactive stakers. (`#2764 <https://github.com/nucypher/nucypher/issues/2764>`__)
- force pull latest tagged image on external geth deployment (`#2766 <https://github.com/nucypher/nucypher/issues/2766>`__)
- Minor memory improvement when collecting staker/worker metrics for prometheus. (`#2785 <https://github.com/nucypher/nucypher/issues/2785>`__)
- Fix bug when generating file for output of events from status & stake cli commands. (`#2786 <https://github.com/nucypher/nucypher/issues/2786>`__)
- Only use public data to generate keystore IDs and filenames. (`#2800 <https://github.com/nucypher/nucypher/issues/2800>`__)
- Fixed WebController bug caused by Path object for TLS/certificate path provided to Hendrix instead of a string. (`#2807 <https://github.com/nucypher/nucypher/issues/2807>`__)
- Avoid crashing the learning loop if there is a problem in the metadata returned by seed nodes. (`#2815 <https://github.com/nucypher/nucypher/issues/2815>`__)
- Fixed a missing timestamp error when a node's status is requested before it participated in metadata exchange. (`#2819 <https://github.com/nucypher/nucypher/issues/2819>`__)
- Fixed a memory leak in Ursula: removed some teacher statistics accumulated over time, and limited the amount of old fleet states stored. (`#2820 <https://github.com/nucypher/nucypher/issues/2820>`__)
- Fixed some occurrences of the old term for ``shares`` (``n``) (`#2829 <https://github.com/nucypher/nucypher/issues/2829>`__)
- Fix an incorrect usage of node object in ``FleetSensor``. (`#2877 <https://github.com/nucypher/nucypher/issues/2877>`__)
- Fix runaway WorkTracker task that ensures operator confirmed transaction occurs but continues running and making web3 requests even after operator already confirmed. (`#2886 <https://github.com/nucypher/nucypher/issues/2886>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Document how worker period commitment works. (`#2776 <https://github.com/nucypher/nucypher/issues/2776>`__)
- Update documentation to reflect new TreasureMap con KFrags design. (`#2833 <https://github.com/nucypher/nucypher/issues/2833>`__)
- Overhaul NuCypher documentation to accommodate the new PRE Application / Threshold Network paradigm. (`#2870 <https://github.com/nucypher/nucypher/issues/2870>`__)
- Add documentation about bonding an operator to a staking provider. (`#2874 <https://github.com/nucypher/nucypher/issues/2874>`__)
- Embed Threshold Network videos within docs. (`#2882 <https://github.com/nucypher/nucypher/issues/2882>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Renames enviorment variable `NUCYPHER_KEYRING_PASSWORD` to `NUCYPHER_KEYSTORE_PASSWORD` (`#2701 <https://github.com/nucypher/nucypher/issues/2701>`__)
- ``m`` and ``n`` parameters can no longer be used in character control and Python API; ``--m`` and ``--n`` are no longer supported by the CLI (``-m`` and ``-n`` still are; the long versions are now ``--threshold`` and ``--shares``) (`#2774 <https://github.com/nucypher/nucypher/issues/2774>`__)
- Removal of treasure map storage functionality and supporting publication APIs from the decentralized network.
  Encrypted treasure maps must be obtained from side channels instead of Ursulas on the network (unless cached). (`#2780 <https://github.com/nucypher/nucypher/issues/2780>`__)
- Remove an unused method of ``Amonia`` (deprecated since we do not store the treasure map on Ursulas anymore) (`#2804 <https://github.com/nucypher/nucypher/issues/2804>`__)
- Removes the Arrangement API for Alice/Ursula negotiations.  Use a simple livliness check during grant-time. (`#2808 <https://github.com/nucypher/nucypher/issues/2808>`__)
- Retires and removes eth/token faucet. (`#2848 <https://github.com/nucypher/nucypher/issues/2848>`__)
- Remove NuCypher DAO specific code since we are now the Threshold DAO. (`#2864 <https://github.com/nucypher/nucypher/issues/2864>`__)
- Removes 'cloudworkers' CLI command in favor of nucypher-ops. (`#2895 <https://github.com/nucypher/nucypher/issues/2895>`__)


Misc
~~~~

- Switch to PyUmbral 0.2 and adjust its usage according to the changed API. (`#2612 <https://github.com/nucypher/nucypher/issues/2612>`__)
- Add disclaimers to ``nucypher stake increase`` and ``nucypher stake merge`` CLI operations to provide warning about
  potential reduced rewards for the first period after stake increase due to a known bug, and the workaround. (`#2693 <https://github.com/nucypher/nucypher/issues/2693>`__)
- Added a more informative error message for ``WorkerPool`` exceptions. (`#2744 <https://github.com/nucypher/nucypher/issues/2744>`__)
- Separated Alice and Publisher roles internally and in relevant public APIs (`#2745 <https://github.com/nucypher/nucypher/issues/2745>`__)
- TreasureMap split into TreasureMap and EncryptedTreasureMap; external methods of Bob and Porter now take the latter, with the parameter named 'encrypted_treasure_map'. SignedTreasureMap is merged with TreasureMap. (`#2773 <https://github.com/nucypher/nucypher/issues/2773>`__)
- Changed the names of ``m`` and ``n`` parameters to ``threshold`` and ``shares`` throughout the API. (`#2774 <https://github.com/nucypher/nucypher/issues/2774>`__)
- Extends policy probationary period until October 31st, 2021. No policies may be created on the network beyond this date. (`#2779 <https://github.com/nucypher/nucypher/issues/2779>`__)
- Umbral dependency bumped to v0.3.0 (`#2798 <https://github.com/nucypher/nucypher/issues/2798>`__)
- Extracting protocol logic into an underlying layer and preparing to move it to Rust. Involves multiple ABI changes (in ``Arrangement``, ``MessageKit``, ``RevocationOrder``, ``EncryptedTreasureMap``, node metadata). In particular, old node metadata will be backward incompatible with the current version, since it now shares the versoning logic with other protocol objects. (`#2802 <https://github.com/nucypher/nucypher/issues/2802>`__)
- Move some cryptographic operations inside the Rust extension. Remove dependency on `umbral` and `coincurve`. (`#2850 <https://github.com/nucypher/nucypher/issues/2850>`__)
- Extend policy probationary period to 2022-6-16T23:59:59.0Z. (`#2873 <https://github.com/nucypher/nucypher/issues/2873>`__)


v5.3.3 (2021-11-24)
-------------------

Bugfixes
~~~~~~~~

- Fixed a memory leak in Ursula; removed some teacher statistics accumulated over time. (`#2826 <https://github.com/nucypher/nucypher/issues/2826>`__)


v5.3.2 (2021-10-15)
-------------------

Bugfixes
~~~~~~~~

- Regenerate Ursula TLS certificates if the become invalid, e.g. become expired. (`#2810 <https://github.com/nucypher/nucypher/issues/2810>`__)


Misc
~~~~

- Extend policy probationary period until December 31st, 2021. No policies may be created on the network that extend beyond this date. (`#2810 <https://github.com/nucypher/nucypher/issues/2810>`__)


v5.3.1 (2021-08-12)
-------------------

Bugfixes
~~~~~~~~

- **Hotfix** - removed Etherchain as a datafeed for now since its format was modified and caused the gas price calculation to fail. (`#2769 <https://github.com/nucypher/nucypher/issues/2769>`__)


v5.3.0 (2021-06-17)
-------------------

Features
~~~~~~~~

- PolicyManager: creating multiple policies in one tx (`#2619 <https://github.com/nucypher/nucypher/issues/2619>`__)
- Adds a new CLI command to show past and present staking rewards, "stake rewards show". (`#2634 <https://github.com/nucypher/nucypher/issues/2634>`__)
- Adds "https://closest-seed.nucypher.network" and "https://mainnet.nucypher.network" as a fallback teacher nodes for mainnet. (`#2657 <https://github.com/nucypher/nucypher/issues/2657>`__)
- Whitespaces in character nicknames are now implicitly replaced with an underscore ("_"). (`#2672 <https://github.com/nucypher/nucypher/issues/2672>`__)
- Added timestamp and date columns to csv output of "nucypher status events" command. (`#2680 <https://github.com/nucypher/nucypher/issues/2680>`__)
- Ursula will now check for active stakes on startup. (`#2688 <https://github.com/nucypher/nucypher/issues/2688>`__)
- Add sub-stake boost information to staking CLI. (`#2690 <https://github.com/nucypher/nucypher/issues/2690>`__)


Bugfixes
~~~~~~~~

- Fixed issues where failing transactions would result in incorrect token allowance and prevent creation of new stakes. (`#2673 <https://github.com/nucypher/nucypher/issues/2673>`__)
- examples/run_demo_ursula_fleet.py - Clean up each DB on shutdown. (`#2681 <https://github.com/nucypher/nucypher/issues/2681>`__)
- Fix a performance regression in ``FleetSensor`` where nodes were matured prematurely (pun not intended) (`#2709 <https://github.com/nucypher/nucypher/issues/2709>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Include annotated description of the worker status page. (`#2665 <https://github.com/nucypher/nucypher/issues/2665>`__)
- Update service fee pricing to reflect correct per period rate since periods are now 7-days. (`#2677 <https://github.com/nucypher/nucypher/issues/2677>`__)
- Add documentation about calculation of staking rewards. (`#2690 <https://github.com/nucypher/nucypher/issues/2690>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Moves "stake collect-reward" to "stake rewards withdraw" command. (`#2634 <https://github.com/nucypher/nucypher/issues/2634>`__)
- Remove IndisputableEvidence (`#2699 <https://github.com/nucypher/nucypher/issues/2699>`__)


Misc
~~~~

- Registry for NuCypher DAO entities. (`#2426 <https://github.com/nucypher/nucypher/issues/2426>`__)
- Added code used to generate the DAO Proposal #1, for reference purposes. (`#2616 <https://github.com/nucypher/nucypher/issues/2616>`__)
- Improves password collection hints while running ``init`` commands. (`#2662 <https://github.com/nucypher/nucypher/issues/2662>`__)
- Extend policy probationary period until August 31st, 2021. No policies may be created on the network beyond this date. (`#2716 <https://github.com/nucypher/nucypher/issues/2716>`__)


v5.2.0 (2021-04-26)
-------------------

Features
~~~~~~~~

- CLI option --duration-periods renamed to --payment-periods. (`#2650 <https://github.com/nucypher/nucypher/issues/2650>`__)


Bugfixes
~~~~~~~~

- Fixed inability to update ursula configuration file due to the keyring not being instantiated - updated logic no longer needs keyring to be instantiated. (`#2660 <https://github.com/nucypher/nucypher/issues/2660>`__)


Misc
~~~~

- Extends policy probationary period until May 31st, 2021.  No policies may be created on the network beyond this date. (`#2656 <https://github.com/nucypher/nucypher/issues/2656>`__)


v5.1.0 (2021-04-15)
-------------------

Features
~~~~~~~~

- Improve UX for character CLI when there are multiple configuration files:
    - If there are multiple possible character configuration files prompt the user to choose
    - If there is only one character configuration file, even if not the default filename, use lone configuration without prompting and print to CLI. (`#2617 <https://github.com/nucypher/nucypher/issues/2617>`__)


Bugfixes
~~~~~~~~

- Ensure that correct configuration filepath is displayed when initializing characters, and add hint about
  using ``--config-file <FILE>`` for subsequent CLI commands if non-default filepath used. (`#2617 <https://github.com/nucypher/nucypher/issues/2617>`__)


v5.0.2 (2021-04-14)
-------------------

Bugfixes
~~~~~~~~

- Fixed incorrect use of genesis value for ``seconds_per_period`` when estimating block number based on period number - applies to prometheus metrics collection and ``nucypher status events``. (`#2646 <https://github.com/nucypher/nucypher/issues/2646>`__)


v5.0.1 (2021-04-14)
-------------------

No significant changes.


v5.0.0 (2021-04-14)
-------------------

Features
~~~~~~~~

- Increase period duration in contracts and handle migration of current stakes to new format. (`#2549 <https://github.com/nucypher/nucypher/issues/2549>`__)
- DAO proposal #1: Improve staker P/L by increasing period duration. (`#2594 <https://github.com/nucypher/nucypher/issues/2594>`__)
- Refinements for pool staking contract (`#2596 <https://github.com/nucypher/nucypher/issues/2596>`__)
- New standalone geth fullnode ansible playbook. (`#2624 <https://github.com/nucypher/nucypher/issues/2624>`__)


Bugfixes
~~~~~~~~

- Accommodate migrated period duration in CLI UX. (`#2614 <https://github.com/nucypher/nucypher/issues/2614>`__)
- cloudworkers more throughoughly cleans up diskspace before updates. (`#2618 <https://github.com/nucypher/nucypher/issues/2618>`__)
- Bob now accepts provider_uri as an optional parameter (`#2626 <https://github.com/nucypher/nucypher/issues/2626>`__)
- Add a default gas limit multiplier of 1.15 for all outgoing ETH transactions (`#2637 <https://github.com/nucypher/nucypher/issues/2637>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Document staking smart contract API and the base staking pool implementation (``PoolingStakingContractV2``). (`#2597 <https://github.com/nucypher/nucypher/issues/2597>`__)


Misc
~~~~

- Change filepath delimiter to dot (".") in Card Storage API (`#2628 <https://github.com/nucypher/nucypher/issues/2628>`__)
- Use constant for loopback address across the codebase. (`#2629 <https://github.com/nucypher/nucypher/issues/2629>`__)


v4.8.2 (2021-03-25)
-------------------

Bugfixes
~~~~~~~~

- Fixes ethereum account selection with ambiguous source in CLI. (`#2615 <https://github.com/nucypher/nucypher/issues/2615>`__)


v4.8.1 (2021-03-24)
-------------------

Bugfixes
~~~~~~~~

- Add ``balance_eth``, ``balance_nu``, ``missing_commitments`` and ``last_committed_period`` to the ``/status`` REST endpoint. (`#2611 <https://github.com/nucypher/nucypher/issues/2611>`__)


v4.8.0 (2021-03-23)
-------------------

Features
~~~~~~~~

- Expanded features for staker and status CLI:
    - Support substake inspection via `nucypher status stakers --substakes`.
    - Automated transaction series for inactive substake removal.
    - Display unlocked NU amount from stakers status.
    - Handle replacement of stuck withdraw transactions with --replace. (`#2528 <https://github.com/nucypher/nucypher/issues/2528>`__)
- Support extended period migration by nodes via work tracker. (`#2607 <https://github.com/nucypher/nucypher/issues/2607>`__)


Bugfixes
~~~~~~~~

- Improved import error feedback and default ssh key path in cloudworkers. (`#2598 <https://github.com/nucypher/nucypher/issues/2598>`__)
- Support geth 1.10.x - Remove chainID from transaction payloads. (`#2603 <https://github.com/nucypher/nucypher/issues/2603>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Document minimum approval and support requirements for NuCypher DAO. (`#2599 <https://github.com/nucypher/nucypher/issues/2599>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Deprecate worker IP address as environment variable (``NUCYPHER_WORKER_IP_ADDRESS``). (`#2583 <https://github.com/nucypher/nucypher/issues/2583>`__)


Misc
~~~~

- Adjust ``Ursula.status_info()`` API to make it easier for ``nucypher-monitor`` to collect data. (`#2574 <https://github.com/nucypher/nucypher/issues/2574>`__)


v4.7.1 (2021-03-02)
-------------------

Bugfixes
~~~~~~~~

- Fixed missing domain parameter causing Ursulas to fail on startup when prometheus is enabled. (`#2589 <https://github.com/nucypher/nucypher/issues/2589>`__)


v4.7.0 (2021-03-02)
-------------------

Features
~~~~~~~~

- New preferable base pooling contract (`#2544 <https://github.com/nucypher/nucypher/issues/2544>`__)
- The output of `nucypher stake events` can be written to a csv file for simpler staker accounting. (`#2548 <https://github.com/nucypher/nucypher/issues/2548>`__)
- Simplifies CLI usage with optional interactive collection of all CLI parameters used during grant, encrypt, and retrieve. (`#2551 <https://github.com/nucypher/nucypher/issues/2551>`__)
- Improved status codes and error messages for various PRE http endpoints (`#2562 <https://github.com/nucypher/nucypher/issues/2562>`__)
- `nucypher status events` can now use event filters and be output to a csv file for simpler accounting. (`#2573 <https://github.com/nucypher/nucypher/issues/2573>`__)


Bugfixes
~~~~~~~~

- Properly handles public TLS certificate restoration; Simplify Ursula construction. (`#2536 <https://github.com/nucypher/nucypher/issues/2536>`__)
- Update the call to ``estimateGas()`` according to the new ``web3`` API (`#2543 <https://github.com/nucypher/nucypher/issues/2543>`__)
- Ensure remote ethereum provider connection is automatically established with characters. Fixes default keyring filepath generation. (`#2550 <https://github.com/nucypher/nucypher/issues/2550>`__)
- Cache Alice's transacting power for later activation. (`#2555 <https://github.com/nucypher/nucypher/issues/2555>`__)
- Prevent process hanging in the cases when the main thread finishes before the treasure map publisher (`#2557 <https://github.com/nucypher/nucypher/issues/2557>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Documentation overhaul with focus on staking node operation (`#2463 <https://github.com/nucypher/nucypher/issues/2463>`__)
- Expands Alice grant example using the python API. (`#2554 <https://github.com/nucypher/nucypher/issues/2554>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Deprecated StakingEscrow features to reduce code size: batch deposits, testContract flag, locking reStake.
  Deployment of StakingEscrow is split in two steps: initial step with stub and final step after all contracts. (`#2518 <https://github.com/nucypher/nucypher/issues/2518>`__)


Misc
~~~~

- Refactor FleetSensor; add "/status/?omit_known_nodes=true" argument; prevent internal constants from leaking into the status page. (`#2352 <https://github.com/nucypher/nucypher/issues/2352>`__)
- WorkLock prometheus metrics are only collected on mainnet. (`#2546 <https://github.com/nucypher/nucypher/issues/2546>`__)
- Sister demo for Finnegan's wake for use on lynx/goerli testnet.
  Alice and Bob API cleanup compelled by EthDenver 2021. (`#2560 <https://github.com/nucypher/nucypher/issues/2560>`__)
- Rework internal transaction signing API for improved thread saftey. (`#2572 <https://github.com/nucypher/nucypher/issues/2572>`__)
- new seed URL for mainnet seeds.nucypher.network
  cloudworkers CLI updates (`#2576 <https://github.com/nucypher/nucypher/issues/2576>`__)
- Extends probationary period for policy creation in the network to 2021-04-30 23:59:59 UTC. (`#2585 <https://github.com/nucypher/nucypher/issues/2585>`__)


v4.6.0 (2021-01-26)
-------------------

Misc
~~~~

- Introduces the Lynx testnet, a more stable environment to learn how to use NuCypher and integrate it into other apps. (`#2537 <https://github.com/nucypher/nucypher/issues/2537>`__)


v4.5.4 (2021-01-22)
-------------------

Bugfixes
~~~~~~~~

- Fix wrong usage of net_version to identify the EthereumClient client chain. (`#2484 <https://github.com/nucypher/nucypher/issues/2484>`__)
- Use eth_chainId instead of net_version to maintain compatibility with geth. (`#2533 <https://github.com/nucypher/nucypher/issues/2533>`__)
- Fixed infinite loop during learning when timing out but known nodes exceeds target. (`#2534 <https://github.com/nucypher/nucypher/issues/2534>`__)


v4.5.3 (2021-01-18)
-------------------

Bugfixes
~~~~~~~~

- Ensure minimum number of available peers for fleet-sourced IP determination and better handling of default teacher unavailability scenarios on startup (`#2527 <https://github.com/nucypher/nucypher/issues/2527>`__)


v4.5.2 (2021-01-15)
-------------------

No significant changes.


v4.5.1 (2021-01-15)
-------------------

No significant changes.


v4.5.0 (2021-01-14)
-------------------

Features
~~~~~~~~

- Compare Ursula IP address with configuration values on startup to help ensure node availability. (`#2462 <https://github.com/nucypher/nucypher/issues/2462>`__)
- Arrangement proposals and policy enactment are performed in parallel, with more nodes being considered as some of the requests fail. This improves granting reliability. (`#2482 <https://github.com/nucypher/nucypher/issues/2482>`__)


Bugfixes
~~~~~~~~

- More logging added for arrangement proposal failures, and more suitable exceptions thrown. (`#2479 <https://github.com/nucypher/nucypher/issues/2479>`__)
- Ignore pending Ethereum transactions for purposes of gas estimation. (`#2486 <https://github.com/nucypher/nucypher/issues/2486>`__)
- Fix rtd build after #2477 (`#2489 <https://github.com/nucypher/nucypher/issues/2489>`__)
-  (`#2491 <https://github.com/nucypher/nucypher/issues/2491>`__, `#2498 <https://github.com/nucypher/nucypher/issues/2498>`__)
- Fix rtd build after #2477 and #2489 (`#2492 <https://github.com/nucypher/nucypher/issues/2492>`__)
- cloudworkers bugfixes, cli args refactor and new "cloudworkers stop" feature. (`#2494 <https://github.com/nucypher/nucypher/issues/2494>`__)
- Gentler handling of unsigned stamps from stranger Ursulas on status endpoint (`#2515 <https://github.com/nucypher/nucypher/issues/2515>`__)
- Restore the re-raising behavior in ``BlockchainInterface._handle_failed_transaction()`` (`#2521 <https://github.com/nucypher/nucypher/issues/2521>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Auto docs generation for smart contracts (`#2477 <https://github.com/nucypher/nucypher/issues/2477>`__)
- Add pricing protocol & economics paper to main repo readme and docs homepage. (`#2520 <https://github.com/nucypher/nucypher/issues/2520>`__)


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

-  (`#2470 <https://github.com/nucypher/nucypher/issues/2470>`__)
- Deprecated manual worker commitments using the CLI. (`#2507 <https://github.com/nucypher/nucypher/issues/2507>`__)


Misc
~~~~

- Relock dependencies and update relock script. (`#2440 <https://github.com/nucypher/nucypher/issues/2440>`__)
- Fixed failing readthedocs build due to dependency mismatches in docs requirements. (`#2496 <https://github.com/nucypher/nucypher/issues/2496>`__)
-  (`#2499 <https://github.com/nucypher/nucypher/issues/2499>`__)
- Ensure that documentation dependencies are updated when standard/development dependencies are updated. (`#2510 <https://github.com/nucypher/nucypher/issues/2510>`__)


v4.4.0 (2020-12-24)
-------------------

Features
~~~~~~~~

- Introduces "Character Cards" a serializable identity abstraction and 'nucypher contacts' CLI to support. (`#2115 <https://github.com/nucypher/nucypher/issues/2115>`__)
- - nucypher cloudworkers now contains a complete and comprehensive set of features for easily managing, backing up and restoring one to many workers (`#2365 <https://github.com/nucypher/nucypher/issues/2365>`__)
- New composite gas strategy that uses the median from three different gas price oracles
  (currently, Etherchain, Upvest and gas-oracle.zoltu.io),
  which behaves more robustly against sporadic errors in the oracles (e.g., spikes, stuck feeds). (`#2420 <https://github.com/nucypher/nucypher/issues/2420>`__)
- Improve gas strategy selection: Infura users now can choose between ``slow``, ``medium`` and ``fast``, and a maximum gas price can be configured with --max-gas-price. (`#2445 <https://github.com/nucypher/nucypher/issues/2445>`__)


Bugfixes
~~~~~~~~

- Slowly try more and more nodes if some of the initial draft for a policy were inaccessible. (`#2416 <https://github.com/nucypher/nucypher/issues/2416>`__)
- Fix bad cli handling in several cloudworkers commands, improved envvar handling. (`#2475 <https://github.com/nucypher/nucypher/issues/2475>`__)


Misc
~~~~

-  (`#2244 <https://github.com/nucypher/nucypher/issues/2244>`__, `#2483 <https://github.com/nucypher/nucypher/issues/2483>`__)
- Solidity compilation refinements (`#2461 <https://github.com/nucypher/nucypher/issues/2461>`__)
- Deprecates internally managed geth process management (`#2466 <https://github.com/nucypher/nucypher/issues/2466>`__)
- Include checksum and IP addresses in exception messages for `Rejected`. (`#2467 <https://github.com/nucypher/nucypher/issues/2467>`__)
- Deprecates managed ethereum client syncing and stale interface methods (`#2468 <https://github.com/nucypher/nucypher/issues/2468>`__)
- Improves console messages for stakeholder CLI initialization and worker startup. (`#2474 <https://github.com/nucypher/nucypher/issues/2474>`__)
- Introduce a template to describe Pull Requests. (`#2476 <https://github.com/nucypher/nucypher/issues/2476>`__)


v4.3.0 (2020-12-08)
-------------------

Features
~~~~~~~~

- Introduces shorthand options for --bob-verifying-key (-bvk), --bob-encrypting-key (-bek) and alice verifying key (-avk) for CLI commands. (`#2459 <https://github.com/nucypher/nucypher/issues/2459>`__)
- Complete interactive collection of policy parameters via alice grant CLI. (`#2460 <https://github.com/nucypher/nucypher/issues/2460>`__)


Bugfixes
~~~~~~~~

- Corrected minimum stake value for --min-stake CLI option (`#2371 <https://github.com/nucypher/nucypher/issues/2371>`__)


Misc
~~~~

- Introduces a probationary period for policy creation in the network, until 2021-02-28 23:59:59 UTC. (`#2431 <https://github.com/nucypher/nucypher/issues/2431>`__)
- Supplies `AccessDenied` exception class for better incorrect password handling. (`#2451 <https://github.com/nucypher/nucypher/issues/2451>`__)
- Maintain compatibility with python 3.6 (removes re.Pattern annotations) (`#2458 <https://github.com/nucypher/nucypher/issues/2458>`__)


v4.2.1 (2020-12-04)
-------------------

Bugfixes
~~~~~~~~

- Removes tests import from constants module causing pip installed versions to crash. (`#2452 <https://github.com/nucypher/nucypher/issues/2452>`__)


v4.2.0 (2020-12-03)
-------------------

Features
~~~~~~~~

- Improve user experience when removing unused substakes (CLI and docs). (`#2450 <https://github.com/nucypher/nucypher/issues/2450>`__)


Bugfixes
~~~~~~~~

- Fix bug in deployer logic while transferring ownership of StakingInterfaceRouter (`#2369 <https://github.com/nucypher/nucypher/issues/2369>`__)
- Allow arbitrary decimal precision when entering NU amounts to nucypher CLI. (`#2441 <https://github.com/nucypher/nucypher/issues/2441>`__)


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Document usage of hardware wallets for signing. (`#2346 <https://github.com/nucypher/nucypher/issues/2346>`__)
- Improvements to the staking guide: extending description of winddown command, other minor corrections. (`#2434 <https://github.com/nucypher/nucypher/issues/2434>`__)


Misc
~~~~

- Rework internal solidity compiler usage to implement "Standard JSON Compile". (`#2439 <https://github.com/nucypher/nucypher/issues/2439>`__)
- Introduces `--config-path` and `--logging-path` CLI flags displaying default nucypher directories (`#2446 <https://github.com/nucypher/nucypher/issues/2446>`__)


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
