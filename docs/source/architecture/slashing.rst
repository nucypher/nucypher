.. _slashing-protocol:

The Slashing Protocol
=====================

The slashing protocol is a preventative mechanism that disincentivizes certain staker actions, whether deliberate or unintentional, to maximize service quality and preserve network health. If prohibited actions (‘violations’) are attributably detected at any moment, the protocol responds by irreversibly deleting (‘slashing’) a portion of the offending staker’s collateral (‘stake’).

At network genesis, the protocol will be able to detect and attribute instances of incorrect re-encryptions returned by Ursulas. The staker controlling the incorrectly re-encrypting Ursula will have their stake reduced by a nominal number of NU tokens.

Violations
----------

In response to an access request by Bob, Ursula must generate a ciphertext that perfectly corresponds to the associated sharing policy (i.e. precisely what Alice intended Bob to receive). If the ciphertext is invalid in this regard, then Ursula is deemed to be incorrectly re-encrypting. Each instance of incorrect re-encryption is an official violation and is individually punished.

There are other ways stakers can compromise service quality and network health, such as extended periods of downtime or ignoring access requests. Unlike incorrect re-encryptions, actions of this kind are not yet reliably attributable. Punishing non-attributable actions may result in unacceptable outcomes or introduce perverse incentives, thus these actions are not yet defined as violations by the slashing protocol.  

Detection
----------

Incorrect re-encryptions are detectable by Bob, who can then send a proof to the protocol to confirm the violation. This is enabled by a bespoke zero-knowledge correctness verification mechanism, which follows these steps:

1. When Alice creates a Kfrag, it includes components to help Ursula prove the correctness of each re-encryption she performs. The Kfrag’s secret component (*bn_key*) is used to perform the re-encryption operation. The Kfrag also comprises public components, including a point commitment on the value of the bn_key.
2. When Ursula receives the Kfrag, she checks it is valid – that the point commitment on the secret component is correct. This ensures that she doesn’t incorrectly re-encrypt due to Alice’s error (or attack).
3. Bob makes a re-encryption request by presenting a capsule to Ursula, and she responds with a Cfrag. This contains the payload (a re-encrypted ciphertext) and a non-interactive zero knowledge proofs of knowledge (NIZK).
4. Bob checks the validity of the Cfrag using the NIZK. He verifies that the point commitment corresponds to the ciphertext. He also checks that the Cfrag was generated using his capsule, by verifying that it was created with the correct public key.
5. If any of the verifications fail, then Bob supplies the ciphertext and NIZK to the Adjudicator contract. The contract runs extensive verification processes, leveraging optimized ECC algorithms.
6. If the invalidity of the Cfrag is confirmed by the Adjudicator contract, the delivery of a faulty Cfrag to Bob is ruled to be an official protocol violation. A penalty is computed and the owner of the offending Ursula has their stake immediately slashed by the penalty amount.

.. image:: ../.static/img/correctness_verification_schematic.png
    :target: ../.static/img/correctness_verification_schematic.png

Penalties
---------

At network genesis, although violations will be detected, attributed and publicly logged, the actual penalty levied will be of nominal size. For each violation, 2*10^-18 NU tokens will be deleted from the offender’s stake. The maximum number of tokens that can be slashed in a given period is limited by the number of blocks processed on Ethereum (assuming 5760 per day and one slash per block) – approximately 10^-12 NU slashable per period.

This nominal penalty is effectively a placeholder until a more complete slashing model is designed and implemented. The genesis penalty is measurable – so staker behavior can be observed – but small enough that it has a negligible impact on the staker’s ability to continue serving the network. If the severity of penalties and logic of the slashing protocol changes, it may involve any combination of the following:

1. Larger penalties levied in absolute terms (number of tokens slashed per violation). This will imply a material disincentive to stakers.

2. Penalties calculated as a percentage of the offender’s stake (i.e. the larger the stake, the greater the number of tokens slashed per violation). This will levy punishments more equitably, regardless of stake size.

3. Ramped penalties, that increase with each successive violation, potentially resetting in a specified number of periods. This will encourage stakers to avoid repeat offences.

4. Temporal limitations on penalties, for example capping the total number of tokens slashabe in each period. This addresses the uneven distribution of effective punishment based on the unpredictable frequency with which a given Bob makes requests to an Ursula. Because Ursulas have no control over Bob’s behavior, they must be given a chance to rectify their worker’s incorrect re-encryptions before their stake is wiped out. This is particularly risky if a Bob is making requests at a high cadence or batches their requests. A limit on the penalty size per day addresses this unfair scenario.

5. Temporary unbonding of Ursula, which forces the staker to forfeit subsidies, work and fees for a specified period. In a simple construction, this punishment would only apply if the Ursula is not servicing any other policies or all Alices consent to the removal of that Ursula from their policies.

6. In conjunction with (5), delegated tokens being automatically returned to delegators. Delegators must proactively re-delegate to the offending staker after a specified time delay has elapsed.

7. Delegated tokens suffering the same fate as staker-owned tokens, as described in (1), (2), and (3). This strongly encourages delegators to choose the most reliable staker(s).  

Impact on stake
---------------

Regardless of how punitive the slashing protocol ends up being, the algorithm will always attempt to preserve the most efficient configuration of the offender's remaining stake, from the perspective of network health. To that end, the lock-up duration of :ref:`sub-stakes` is taken into account when selecting the portion(s) of stake to slash.

An entire stake consists of:

    * unlocked tokens which the staker can withdraw at any moment
    * tokens locked for a specific period

In terms of how the stake is slashed, unlocked tokens are the first portion of the stake to be slashed. After that, if necessary, locked sub-stakes are decreased in order based on their remaining lock time, beginning with the shortest. The shortest sub-stake is decreased, and if the adjustment of that sub-stake is insufficient to fulfil the required punishment sum, then the next shortest sub-stake is decreased, and so on. Sub-stakes that begin in the next period are checked separately.

Sub-stakes for past periods cannot be slashed, so only the periods from the current period onward can be slashed. However, by design sub-stakes can't have a starting period that is after the next period, so all future periods after the next period will always have an amount of tokens less than or equal to the next period. The current period still needs to be checked since its stake may be different than the next period. Therefore, only the current period and the next period need to be checked for slashing.

Overall the slashing algorithm is as follows:

#. Reduce unlocked tokens

#. If insufficient, slash sub-stakes as follows:

    a. Calculate the maximum allowed total stake for any period for the staker ::

        max_allowed_stake = pre_slashed_total_stake - slashing_amount

       Therefore, for any period moving forward the sum of sub-stakes for that period cannot be more than ``max_allowed_stake``.
    b. For the current and next periods ensure that the amount of locked tokens is less than or equal to ``max_allowed_stake``. If not, then reduce the shortest sub-stake to ensure that this occurs; then the next shortest and so on, as necessary for the period.
    c. Since sub-stakes can extend over multiple periods and can only have a single fixed amount of tokens for all applicable periods (see :ref:`sub-stakes`), the resulting amount of tokens remaining in a sub-stake after slashing is the minimum amount of tokens it can have across all of its relevant periods. To clarify, suppose that a sub-stake is locked for periods ``n`` and ``n+1``, and the slashing algorithm first determines that the sub-stake can have 10 tokens in period ``n``, but then it can only have 5 tokens in period ``n+1``. In this case, the sub-stake will be slashed to have 5 tokens in both periods ``n`` and ``n+1``.
    d. The above property of sub-stakes means that there is the possibility that the total amount of locked tokens for a particular period could be reduced to even lower than the ``max_allowed_stake``. Therefore, the slashing algorithm may create new sub-stakes on the staker's behalf to utilize tokens in the earlier period, when a sub-stake is needed to be reduced to an even lower value because of the next period. In the example above in c), the sub-stake was reduced to 5 tokens because of period ``n+1``, so there are 5 "extra" tokens `(10 - 5)` available in period ``n`` that can still be staked; hence, a new sub-stake with 5 tokens would be created to utilize these tokens in period ``n``. This benefits both the staker, by ensuring that their remaining tokens are efficiently utilized, and the network by maximizing its health.


To reinforce the algorithm, consider the following example stake and different slashing scenarios:

**Example:**

    A staker has 1000 tokens:
        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 200 tokens for 2 periods
        * 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods. The 3rd sub-stake is locked for the next period but won't be used as a deposit for "work" until the next period begins.
        * 200 tokens in an unlocked state (still staked, but can be freely withdrawn).

    .. code::

            stake
            ^
            |
         800|     +----+
            |     | 3rd|
         700+-----+----+
            |          |
         600|    2nd   +-------------+
            |          |     3rd     |
         500+----------+-------------+----------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->

Penalty Scenarios:

* *Scenario 1*: Staker incurs penalty calculated to be worth **100 tokens**:

    Only the unlocked tokens will be reduced; from 200 to 100. The values of locked sub-stakes will therefore remain unchanged in this punishment scenario.

    Result:

        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 200 tokens for 2 periods
        * 3rd sub-stake = 100 tokens locked starting from the next period
        * 100 tokens in an unlocked state

* *Scenario 2*: Staker incurs penalty calculated to be worth **300 tokens**:

    The unlocked tokens can only cover 200 tokens worth of the penalty. Beyond that, the staker has 700 tokens currently locked and 100 tokens that will lock in the next period, meaning 800 tokens will be locked in total. In this scenario, we should reduce amount of locked tokens for the next period and leave unchanged locked amount in the current period. The 3rd sub-stake would be suitable to be reduced except that it's not the shortest, in terms of its unlock date. Instead, the 2nd sub-stake – the shortest (2 periods until unlock) – is reduced to 100 tokens and a new sub-stake with 100 tokens is added which is only active in the current period.

    Result:

        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 100 tokens for 2 periods
        * 3rd sub-stake = 100 tokens locked starting from the next period for 5 periods
        * 4rd sub-stake = 100 tokens for 1 period
        * Remaining 0 tokens

    .. code::

             stake
             ^
             |
          800|     +----+
             |     | 3rd|
        700- +-----+----+ - - - - - - - - - - - - -
             |          |
          600|    2nd   +-------------+
             |          |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->

             stake
             ^
             |
             |
        700- | - - +----+ - - - - - - - - - - - - -
             |     | 3rd|
          600+-----+----+-------------+
             |    2nd   |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->

             stake
             ^
             |
             |
        700- +-----+----+ - - - - - - - - - - - - -
             | 4th | 3rd|
          600+-----+----+-------------+
             |    2nd   |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->

   
* *Scenario 3*: Staker incurs penalty calculated to be worth **400 tokens**:

    The difference between this and the previous scenario is that the current period's sum of locked tokens is also reduced. The first step is to reduce the 2nd sub-stake to 100 tokens. Then, the next period is adjusted – the shortest sub-stake is still the 2nd – and it is reduced from 100 to zero for the next period. Notably, this would have the same result if we changed the duration of the 2nd sub-stake from 2 periods to 1 and the other sub-stakes remained unchanged.

    Result:

        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 100 tokens for 1 period
        * 3rd sub-stake = 100 tokens locked starting from the next period
        * Remaining 0 tokens

    .. code::

             stake
             ^
             |
          800|     +----+
             |     | 3rd|
          700+-----+----+
             |          |
        600- |- -2nd- - +-------------+ - - - - - -
             |          |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->


             stake
             ^
             |
          700|     +----+
             |     | 3rd|
        600- +-----+----+-------------+ - - - - - -
             |    2nd   |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->


             stake
             ^
             |
        600- +-----+------------------+ - - - - - -
             | 2nd |       3rd        |
          500+-----+------------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->

 
* *Scenario 4*: Staker incurs penalty calculated to be worth **600 tokens**:

    The unlocked tokens, the 3rd sub-stake, and the shortest sub-stake (2nd) are all reduced to zero. This is not quite enough, so the next shortest sub-stake, the 1st, is also reduced from 500 to 400.

    Result:

        * 1st sub-stake = 400 tokens locked for 10 periods
        * 2nd sub-stake = 0 tokens for 2 periods
        * 3rd sub-stake = 0 tokens locked starting from the next period
        * Remaining 0 tokens

    .. code::

             stake
             ^
             |
          800|     +----+
             |     | 3rd|
          700+-----+----+
             |          |
          600|    2nd   +-------------+
             |          |     3rd     |
          500+----------+-------------+----------+
        400- | - - - - - - - - - - - - - - - - - | -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->

             stake
             ^
             |
          600|     +------------------+
             |     |       3rd        |
          500+-----+------------------+----------+
        400- | - - - - - - - - - - - - - - - - - | -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->


             stake
             ^
             |
          500|     +------------------+
             |     |       3rd        |
        400- +-----+------------------+----------+ -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->


             stake
             ^
             |
        400- +-----------------------------------+ -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
