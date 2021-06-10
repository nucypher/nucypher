Glossary
========

.. _Umbral: https://github.com/nucypher/umbral-doc/blob/master/umbral-doc.pdf

.. glossary::

    Alice
      *"The Data Owner"* :term:`Character` - retains full control over the data encrypted for her and determines whom to share the data with.

    Bob
      *"The Data Recipient"* :term:`Character` - the data recipient that :term:`Alice` intends to share data with.

    Capsule
      Encrypted symmetric key (:term:`KEM`) that is eventually re-encrypted.

    cFrag
      A fragment of ciphertext that is a partial re-encryption produced by a :term:`kFrag` operation on a :term:`Capsule`.

    Character
      A common term for any entity fulfilling a particular role in our cryptographic narrative.

    DEM
      Data encapsulation mechanism - data encrypted with a symmetric key.

    Enrico
      *"The Encryptor"* :term:`Character` - a data source that encrypts data on behalf of :term:`Alice` and produces a :term:`MessageKit`.

    Felix
      *"The Faucet"* :term:`Character` - provides *testnet* NU tokens for nodes on the test NuCypher Network.

    KEM
      Key encapsulation mechanism - a symmetric key encrypted with an asymmetric key

    kFrag
      A fragment of a :term:`Re-encryption Key`.

    Label
      A title for a classification/categorization of data according to how it is intended to be shared.

    MessageKit
      The ciphertext (data encrypted with a symmetric key) and the :term:`Capsule` (encrypted symmetric key) that are stored together.

    NU
      The NuCypher token used by nodes for staking.

    NuNit
      1 NU = 10\ :sup:`18` NuNits.

    Period
      A timeframe of approximately 7 days in the NuCypher Network. This parameter is used as a minimum unit for policy
      duration, and is also the cadence with which workers must make an on-chain commitment to being online and
      available. Note that period durations were 24 hours in the genesis (previous) protocol and could change again in the
      future.

    PKE
      Public-key encryption.

    Porter
      A web service that is the conduit between applications (platform-agnostic) and the nucypher network, that
      performs nucypher protocol operations on behalf of Alice and Bob.

    PRE
      Proxy re-encryption.

    Re-encryption Key
      A key that facilitates the transformation of ciphertext from one encryption key to another.

    Stake
      A quantity of tokens and escrow duration in periods.

    Staker
      An account that holds NU tokens and performs staking-related operations on the blockchain.

    Stamp
      The public key for a :term:`Character`'s signing key pair.

    Treasure Map
      The locations of :term:`Ursulas<Ursula>` that have the relevant :term:`kFrags<kFrag>` for a policy. :term:`Bob` will use the treasure map to determine which :term:`Ursulas<Ursula>` to contact to re-encrypt the data :term:`Alice` has shared with him.

    Umbral
      NuCypher's threshold proxy re-encryption scheme - it takes standard :term:`PRE` and increases security and performance. See Umbral_.

    Ursula
      *"The Proxy in PRE"* :term:`Character` - the nodes on the NuCypher Network that stand ready to re-encrypt data in exchange for payment in fees and token rewards; they enforce the access policy created by :term:`Alice`.

    Worker
      An account that is actively doing work in the network as an :term:`Ursula` node. A worker is bonded to, and performs work on behalf of, a :term:`Staker`.

    WorkLock
      NuCypher's permissionless token distribution mechanism.
