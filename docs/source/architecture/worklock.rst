.. _worklock-architecture:

========
WorkLock
========

.. important::

    Participation in WorkLock is now closed, but since NU is an ERC-20 token, it can be purchased through exchanges.

Overview
--------

`WorkLock` is a novel, permissionless decentralized network node setup mechanism, developed at NuCypher, which requires
participants to temporarily escrow ETH and operate NuCypher nodes in order to be allocated NU, the native
cryptocurrency of the NuCypher network that enables node operation.

WorkLock is designed to onboard threshold cryptography nodes to the live NuCypher network using a process that selects
participants who are most likely to strengthen and sustain the network by committing to staking and running active nodes.

The WorkLock begins with an escrow period, during which anyone seeking to operate a NuCypher node can send
ETH to the WorkLock contract to be temporarily escrowed on-chain.
At any time during the escrow period, WorkLock participants can cancel their participation to forgo NU and recoup
their escrowed ETH immediately.

Once the escrow period closes, the WorkLock contract does not accept more ETH, but will still accept cancellations
during an additional time window (the "cancellation window").  At the end of this cancellation period,
the allocation period begins and stake-locked NU are allocated to participants in the form of non-transferable stakes.
These stakes are designed for the limited and explicit purpose of running threshold cryptography nodes on the live NuCypher network.
Stake-locked NU will be allocated at network launch according to the following principles:

 - All of the NU held by WorkLock will be allocated to network nodes in non-transferable stakes designed to enable node operation.
 - All ETH escrows must be greater than or equal to the minimum allowed escrow.
 - For each escrow, the surplus above the minimum allowed escrow is called the `bonus`; all escrows are composed of a `base` escrow (fixed minimum) and a `bonus` escrow (variable amount).
 - Each participant will receive at least the minimum amount of staked NU needed to operate a network node.
 - Once all participants have been allocated the minimum amount of NU, each participant with a `bonus` will be allocated a portion of the remaining NU,
   allocated pro rata across all participants, taking into consideration only their bonus ETH amounts.
 - If the resulting NU allocated to a participant is above the maximum allowed NU needed to operate a network node, then such a participant has their escrow partially refunded until the corresponding amount of NU is within the allowed limits for node operation.

Finally, if WorkLock participants use that stake-locked NU to run a node and provide threshold cryptography services on the live network for a minimum of six months,
the NU will subsequently unlock and their temporarily escrowed ETH will be returned in full.
Participants that fail to successfully run a NuCypher network node for six months of the live network will not receive stake-rewarded NU and their ETH will remain escrowed in the
WorkLock contract.


Hypothetical WorkLock Scenarios
-------------------------------

.. important::

    These examples use **hypothetical** values that allow for easier illustration and calculations. The specified
    WorkLock properties in the examples are **not** intended to be reflective of what actual values will be.

For each scenario, assume the following **hypothetical WorkLock properties**:

 #. WorkLock holds 225,000,000 NU and the minimum escrow is 5 ETH.
 #. The minimum amount of NU required to stake is 15,000 NU and the maximum stake size is 30,000,000 NU.
 #. The total number of participants is 1000 (including you) with a total of 50,000 ETH escrowed (including your escrow).
 #. For our purposes, a `whale` escrow is an escrow that causes the calculated stake size to be larger than the maximum stake size (30,000,000 NU).

.. note::

    To reduce complexity, calculations are performed in a step-wise manner which may lead to minor rounding differences
    in the determined values.


Scenario 1: Resulting stake size does not exceed maximum stake size (no whale escrows)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**You submit an escrow of 32 ETH i.e. 5 ETH minimum + 27 bonus ETH.**

*How many NU would be allocated to your network node?*

 - Each of the 1000 participants (including you) would be allocated at least the minimum NU to stake = 15,000 NU
 - Remaining NU in WorkLock after minimum allocation is

        .. math::

            225,000,000 NU - (15,000 NU \times 1000 \,participants) = 210,000,000 NU

 - Bonus ETH supply (i.e. total ETH not including minimum escrows) is

        .. math::

            50,000 ETH - (5 ETH \times 1000 \,participants) = 45,000 ETH

 - Your bonus portion of the bonus ETH supply is

        .. math::

            \frac{27 ETH}{45,000 ETH} = 0.06\%

 - Your allocation of the remaining NU is

        .. math::

            0.06\% \times 210,000,000 NU = 126,000 NU


**Total NU received = 15,000 NU + 126,000 NU = 141,000 NU**

Scenario 2: Resulting stake size exceeds maximum stake size (1 whale escrow)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**You submit an escrow of 6,755 ETH i.e. 5 ETH minimum + 6,750 bonus ETH.**

*How many NU would be allocated to your network node?*

 - Each of the 1000 participants (including you) would be allocated at least the minimum NU to stake = 15,000 NU
 - Remaining NU in WorkLock after minimum allocation is

        .. math::

            225,000,000 NU - (15,000 NU \times 1000 \,participants) = 210,000,000 NU

 - Bonus ETH supply (i.e. total ETH not including minimum escrows) is

        .. math::

            50,000 ETH - (5 ETH \times 1000 \,participants) = 45,000 ETH

 - Your bonus allocation of the bonus ETH supply is

        .. math::

            \frac{6,750 ETH}{45,000 ETH} = 15\%

 - Your allocation of the remaining NU is

        .. math::

            15\% \times 210,000,000 NU = 31,500,000 NU


However, the total amount of NU to be allocated is 15,000 NU + 31,500,000 NU = 31,515,000 NU which is greater than
the maximum stake amount (30,000,000 NU). Therefore, the amount of NU allocated to you needs to be reduced,
and some of your bonus ETH refunded.

 - Typically the calculation for the NU allocated from the bonus portion is

        .. math::

            \frac{\text{your bonus ETH}}{\text{bonus ETH supply}} \times \text{remaining NU bonus supply}

 - The additional complication here is that refunding bonus ETH reduces your bonus ETH **AND** the bonus ETH supply since the
   bonus ETH supply includes the bonus ETH portion of your escrow.
 - A more complicated equation arises for the bonus part of the calculation, where `x` is the refunded ETH:

        .. math::

            \text{stake size} = \frac{\text{(your bonus ETH - x)}}{\text{(bonus ETH supply - x)}} \times \text{remaining NU}

 - Since you will be allocated a 15,000 NU minimum, and the maximum stake size is 30,000,000 NU, the most you can be allocated from the remaining NU is

        .. math::

            30,000,000 NU - 15,000 NU = 29,985,000 NU

 - Therefore using values in the equation above yields

        .. math::

            29,985,000 NU = \frac{6,750 ETH - x ETH}{45,000 ETH - x ETH} \times 210,000,000 NU

 - Reorganizing the equation

        .. math::

            x &= \frac{6,750 ETH \times 210,000,000 NU - 45,000 ETH \times 29,985,000 NU}{210,000,000 NU - 29,985,000 NU} \\
              &\approx 378.72 ETH

 - Therefore, your final bonus escrow is

        .. math::

            6,750 ETH - 378.72 ETH \approx 6,371.28 ETH

 - Your portion of the bonus ETH supply is

        .. math::

            \frac{6,371.28}{(45,000 ETH - 378.72 ETH)} \approx 14.279\%

 - Your allocation of the remaining NU is

        .. math::

            14.279\% \times 210,000,000 NU \approx 29,985,000 NU

**Total NU allocated ~ 15,000 NU + 29,985,000 NU (rounding) ~ 30,000,000 NU, and refunded ETH ~ 378.72 ETH**


Scenario 3: Resulting stake size exceeds maximum stake size (2 whale escrows)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Someone else submitted an escrow of 6,108 ETH i.e. 5 ETH + 6,100 bonus ETH; we'll call them "whale_1".**

**You submit an escrow of 6,755 ETH i.e. 5 ETH minimum + 6,750 bonus ETH; you are "whale_2".**

*How many NU would be allocated to your network node?*

 - Each of the 1000 participants (including you) would receive at least the minimum NU to stake = 15,000 NU
 - Remaining NU in WorkLock after minimum allocation is

        .. math::

            225,000,000 NU - (15,000 NU \times 1000 \,participants) = 210,000,000 NU

 - Bonus ETH supply (i.e. total ETH not including minimum escrows) is

        .. math::

            50,000 ETH - (5 ETH \times 1000 \,participants) = 45,000 ETH

 - Your portion of the bonus ETH supply is

        .. math::

            \frac{6,750 ETH}{45,000 ETH} = 15\%

 - Your allocation of the remaining NU is

        .. math::

            15\% \times 210,000,000 NU= 31,500,000 NU

However, the total amount of NU to be allocated to receive is 15,000 NU + 31,500,000 NU = 31,515,000 NU which is greater than
the maximum stake amount (30,000,000 NU).

 -  From the previous scenario, the equation for the bonus part of the calculation is as follows, where `x` is the refunded ETH

        .. math::

            \text{stake size} = \frac{\text{(your bonus ETH - x)}}{\text{(bonus ETH supply - x)}} \times \text{remaining NU}

 - Additionally, there is more than one whale escrow, which would also cause the bonus ETH supply to reduce as well.
 - Instead the following `whale resolution` algorithm is employed:

    #. Select the smallest whale bonus ETH escrow; in this case 6,390 ETH from `whale_1` < 6,750 ETH from `whale_2`
    #. Equalize the bonus ETH whale escrows for all other whales (in this case, just `whale_2` i.e. just you) to be the smallest whale bonus escrow i.e. 6,390 ETH in this case
    #. Since your bonus ETH escrow is > 6,390 ETH, you will be refunded

        .. math::

            6,750 ETH - 6,390 ETH = 360 ETH

    #. This reduces the resulting bonus ETH supply which will now be

        .. math::

            45,000 ETH - 360 ETH = 44,640 ETH

    #. We now need to calculate the bonus ETH refunds based on the updated bonus ETH supply, and the maximum stake size.
    #. Remember that everyone is allocated a 15,000 NU minimum, and the maximum stake size is 30,000,000 NU, so the most that can be allocated to you from the remaining NU is

        .. math::

            30,000,000 NU - 15,000 NU = 29,985,000 NU

    #. Since we have multiple whales, our equation is the following , where `n` is the number of whale escrows

        .. math::

            x = \frac{\text{(min whale escrow} \times \text{NU supply - eth_supply} \times \text{max stake)}}{\text{(NU supply - n} \times \text{max stake)}}

    #. Plugging in values

        .. math::

            x &= \frac{(6,390 ETH \times 210,000,000 NU - 44,640 ETH \times 29,985,000 NU)}{(210,000,000 NU - 2 \times 29,985,000 NU)} \\
              &\approx 22.46 ETH

        - hence each whale gets additionally refunded ~ 22.46 ETH

    #. Therefore,

        - `whale_1` is refunded ~ 22.46 ETH
        - `whale_2` (i.e. you) is refunded ~ 22.46 ETH + 360 ETH (from Step 3) ~ 382.46 ETH

    #. Based on the refunds

        - The bonus escrows for the whales will now be equalized:

            - `whale_1` bonus ~ 6,390 ETH - 22.46 ETH ~ 6,367.54 ETH
            - `whale_2` bonus ~ 6,750 ETH - 382.46 ETH ~ 6,367.54 ETH

        - The updated bonus ETH supply will be

            .. math::

                45,000 ETH - (22.46 ETH + 382.46 ETH) \approx 44,595.08 ETH

    #. Each whale's portion of the bonus ETH supply is therefore

            .. math::

                \frac{6,367.54 ETH}{44,595.08 ETH} \approx 14.279\%

    #. And each whale's allocation of the remaining NU is

            .. math::

                14.279\% \times 210,000,000 NU \approx 29,985,900 NU

**Total NU allocated ~ 15,000 NU + 29,985,900 NU (rounding) ~ 30,000,000 NU, and refunded ETH ~ 382.46 ETH**


.. note::

    In Scenarios 2 and 3, you will notice that the bonus ETH supply was reduced. This produces a very subtle situation -
    for previous non-whale participants (escrows in the original bonus ETH supply that did not produce a stake larger than the
    maximum stake) their escrows remained unchanged, but the bonus ETH supply was reduced. This means that some participants that
    were not originally whales, may become whales once the bonus ETH supply is reduced since their proportion of the
    bonus pool increased. Therefore, the `whale resolution` algorithm described in Scenario 3 may be repeated for
    multiple rounds until there are no longer any whales. To keep the explanation simple, both Scenarios 2 and 3 ignore
    such a situation since the calculations become even more complex.
