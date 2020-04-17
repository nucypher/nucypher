.. _worklock-guide:

==============
WorkLock Guide
==============

Overview
--------

`WorkLock` is a novel, permissionless token distribution mechanism, developed at NuCypher, which requires participants to stake ETH and maintain NuCypher nodes in order to receive NU tokens.

WorkLock offers specific advantages over ICO or airdrop as a distribution mechanism, chiefly: it selects for participants who are most likely to strengthen the network because they commit to staking and running nodes.

The WorkLock begins with an open bidding period, during which anyone seeking to participate can send ETH to the WorkLock contract to be escrowed on-chain.
At any time, WorkLock participants can cancel their bid to forgo NU and recoup their escrowed ETH immediately.
Once the bidding period closes, the WorkLock contract does not accept more bids, but it will still accept cancellations during an additional time window.
At the end of this cancellation period, stake-locked NU will be distributed according to the following principles:

 - All of the tokens held by WorkLock will be distributed.
 - All bids must be greater than or equal to the minimum allowed bid.
 - For each bid, the surplus above the minimum allowed bid is called the `bonus`; all bids are composed of a minimum bid (fixed amount) and a `bonus` (variable amount).
 - Each bidder will receive at least the minimum amount of NU needed to stake.
 - Once all bidders have been assigned the minimum amount of NU, each bidder with a `bonus` will receive a portion of the remaining NU, distributed pro rata across all participants, taking into consideration only their bonus amounts.
 - If the resulting NU amount distributed to a bidder is above the maximum allowed NU to stake, then such a bidder has their bid partially refunded until the corresponding amount of NU is within the allowed limits.

Finally, if WorkLock participants use that stake-locked NU to run a node, the NU will eventually unlock and their escrowed ETH will be returned in full.


Hypothetical Bidding Scenarios
------------------------------

.. note::

    To reduce complexity, calculations are performed in a step-wise manner and may lead to minor rounding differences
    in the determined values.

For each scenario, assume that:

 #. WorkLock holds 280,000,000 NU tokens and the minimum bid is 15 ETH.
 #. The minimum amount of NU required to stake is 15,000 NU and the maximum stake size is 4,000,000 NU.
 #. The total number of bidders is 1000 bidders (including you) with a total of 50,000 ETH committed (including your bid).
 #. For our purposes, a `whale` bid is a bid that causes the calculated stake size to be larger than the maximum stake size (4,000,000 NU).


Scenario 1: Resulting stake size does not exceed maximum stake size
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**You submit a bid of 22 ETH i.e. 15 ETH minimum bid + 7 ETH bonus.**

*How many NU tokens would you receive?*

 - Each of the 1000 bidders (including you) would receive at least the minimum NU to stake = 15,000 NU
 - Remaining NU in WorkLock after minimum distribution is

        .. math::

            280,000,000 NU - (15,000 NU \times 1000 \,bidders) = 265,000,000 NU

 - Bonus ETH pool (i.e. total ETH not including minimum amounts) is

        .. math::

            50,000 ETH - (15 ETH \times 1000 \,bidders) = 35,000 ETH

 - Your bonus portion of the ETH bonus pool is

        .. math::

            \frac{7 ETH}{35,000 ETH} = 0.02\%

 - Your portion of remaining NU is

        .. math::

            0.02\% \times 265,000,000 NU= 53,000 NU


**Total NU tokens received = 15,000 NU + 53,000 NU = 68,000 NU**

Scenario 2: Resulting stake size exceeds maximum stake size (1 whale bid)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**You submit a bid of 715 ETH i.e. 15 ETH minimum bid + 700 ETH bonus.**

*How many NU tokens would you receive?*

 - Each of the 1000 bidders (including you) would receive at least the minimum NU to stake = 15,000 NU
 - Remaining NU in WorkLock after minimum distribution is

        .. math::

            280,000,000 NU - (15,000 NU \times 1000 \,bidders) = 265,000,000 NU

 - Bonus ETH pool (i.e. total ETH not including minimum amounts) is

        .. math::

            50,000 ETH - (15 ETH \times 1000 \,bidders) = 35,000 ETH

 - Your bonus portion of the ETH bonus pool is

        .. math::

            \frac{700 ETH}{35,000 ETH} = 2\%

 - Your portion of remaining NU is

        .. math::

            2\% \times 265,000,000 NU= 5,300,000 NU


However, the total amount of NU tokens to receive is 15,000 NU + 5,300,000 NU = 5,315,000 NU which is greater than
the maximum stake amount (4,000,000 NU). Therefore, the amount of NU tokens distributed to you needs to be reduced,
and some of your ETH refunded.

 - Typically the calculation for the NU received from the bonus portion is

        .. math::

            \frac{\text{your bonus ETH}}{\text{ETH bonus pool}} \times \text{remaining NU tokens}

 - The additional complication here is that refunding ETH reduces your bonus ETH **AND** the bonus ETH pool (35,000 ETH in this example) since the bonus ETH pool includes the bonus ETH portion of your bid.
 - A more complicated equation arises for the bonus part of the calculation, where `x` is the refunded ETH:

        .. math::

            \text{stake size} = \frac{\text{(your bonus ETH - x)}}{\text{(ETH bonus pool - x)}} \times \text{remaining NU tokens}

 - Since you will receive a 15,000 NU minimum, and the maximum stake size is 4,000,000 NU, the most you can receive from the remaining NU is

        .. math::

            4,000,000 NU - 15,000 NU = 3,985,000 NU

 - Therefore using values in the equation above yields

        .. math::

            3,985,000 NU = \frac{700 ETH - x ETH}{35,000 ETH - x ETH} \times 265,000,000 NU

 - Reorganizing the equation

        .. math::

            x = \frac{700 ETH \times 265,000,000 NU - 35,000 ETH \times 3,985,000 NU}{265,000,000 NU - 3,985,000 NU} \approx 176.33 ETH

 - Therefore, your final bonus bid is

        .. math::

            700 ETH - 176.33 ETH \approx 523.67 ETH

 - Your bonus portion of the ETH bonus pool is

        .. math::

            \frac{523.67}{(35,000 ETH - 176.33 ETH)} \approx 1.504\%

 - Your portion of remaining NU is

        .. math::

            1.504\% \times 265,000,000 NU \approx 3,985,006.46 NU

**Total NU tokens received ~ 15,000 NU + 3,985,006.46 NU (rounding) ~ 4,000,000 NU, and refunded ETH ~ 176.33 ETH**


Scenario 3: Resulting stake size exceeds maximum stake size (2 whale bids)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Someone else submitted a bid of 715 ETH (15 ETH + 700 ETH bonus); we'll call them `whale_1`.**

**You submit a bid of 785 ETH i.e. 15 ETH minimum bid + 770 ETH bonus; you are `whale_2`.**

*How many NU tokens would you receive?*

 - Each of the 1000 bidders (including you) would receive at least the minimum NU to stake (15,000 NU)
 - Remaining NU in WorkLock after minimum distribution is

        .. math::

            280,000,000 NU - (15,000 NU \times 1000 \,bidders) = 265,000,000 NU

 - Bonus ETH pool (i.e. total ETH not including minimum amounts) is

        .. math::

            50,000 ETH - (15 ETH \times 1000 \,bidders) = 35,000 ETH

 - Your bonus portion of the ETH bonus pool is

        .. math::

            \frac{770 ETH}{35,000 ETH} = 2.2\%

 - Your portion of remaining NU is

        .. math::

            2.2\% \times 265,000,000 NU= 5,830,000 NU

However, the total amount of NU tokens to receive is 15,000 NU + 5,830,000 NU = 5,845,000 NU which is greater than
the maximum stake amount (4,000,000 NU).

 -  From the previous scenario, the equation for the bonus part of the calculation is as follows, where `x` is the refunded ETH

        .. math::

            \text{stake size} = \frac{\text{(your bonus ETH - x)}}{\text{(ETH bonus pool - x)}} \times \text{remaining NU tokens}

 - Additionally, there is more than one whale bid, which would also cause the ETH bonus pool to reduce as well
 - Instead the following `whale resolution` algorithm is followed:

    #. Select the smallest whale bonus ETH bid - in this case 700 ETH from `whale_1` < 770 ETH from `whale_2`
    #. Equalize the bonus ETH whale bids for all other whales (in this case, just `whale_2` i.e. just you) to all be the smallest whale bonus bid i.e. 700 ETH in this case
    #. Since your bid (whale_2) is > 700 ETH, you will be refunded

        .. math::

            770 ETH - 700 ETH = 70 ETH

    #. This reduces the resulting bonus ETH pool which will now be

        .. math::

            35,000 ETH - 70 ETH = 34,930 ETH

    #. We now need to calculate the refunds based on the updated ETH bonus pool, and the maximum stake size.
    #. Remember that everyone receives a 15,000 NU minimum, and the maximum stake size is 4,000,000 NU, so the most you can receive from the remaining NU is

        .. math::

            4,000,000 NU - 15,000 NU = 3,985,000 NU

    #. Since we have multiple bidders, our equation is the following , where `n` is the number of whale bidders

        .. math::

            x = \frac{\text{(min whale bid} \times \text{token supply - eth_supply} \times \text{max stake)}}{\text{(token supply - n} \times \text{max stake)}}

    #. Plugging in values

        .. math::

            x = \frac{(700 ETH \times 265,000,000 NU - 34,930 ETH \times 3,985,000 NU)}{(265,000,000 NU - 2 \times 3,985,000 NU)} \approx 180.15 ETH

        - hence each whale gets refunded ~ 180.15 ETH

    #. Therefore

        - `whale_1` is refunded ~ 180.15 ETH
        - `whale_2` (i.e. you) is refunded ~ 180.15 ETH + 70 ETH (from Step 3) = 250.15 ETH

    #. Based on the refunds

        - The bonus bids for the whales will now be equalized:

            - `whale_1` bonus bid = 700 ETH - 180.15 ETH = 519.85 ETH
            - `whale_2` bonus bid = 770 ETH - 250.15 ETH = 519.85 ETH

        - The updated ETH Bonus Pool will be

            .. math::

                35,000 ETH - (180.15 ETH + 250.15 ETH) = 34,569.70 ETH

    #. Each whale's portion of the ETH bonus pool is therefore

            .. math::

                \frac{519.85 ETH}{34,569.70 ETH} \approx 1.504\%

    #. And each whale's portion of the remaining NU is

            .. math::

                1.504\% \times 265,000,000 NU = 3,984,999.86 NU

**Total NU tokens received ~ 15,000 NU + 3,984,999.86 NU ~ 3,999,999.86 NU, and refunded ETH ~ 176.33 ETH**


.. note::

    In Scenario 1 and 2, you will notice that the ETH bonus pool has been reduced. This produces a very subtle situation -
    for previous non-whale bids (bids that in the original ETH bonus pool that did not produce a stake larger than the
    maximum stake) their bids remained unchanged, but the ETH bonus pool was reduced. This means that some bids that
    were not whales, may become whales once the ETH bonus pool is reduced since their proportion of the bonus pool
    increased. Therefore, the `whale resolution` algorithm described in Scenario 2 may be repeated for multiple rounds
    until there are no longer any whales. To keep the explanation simple, both Scenario 1 and Scenario 2 ignore this
    situation since the calculations become even more complex.


WorkLock CLI
------------

The ``nucypher worklock`` CLI command provides the ability to participate in WorkLock. To better understand the
commands and their options, use the ``--help`` option.

All ``nucypher worklock`` commands share a similar structure:

.. code::

    (nucypher)$ nucypher worklock <ACTION> [OPTIONS] --network <NETWORK> --provider <YOUR PROVIDER URI>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/ubuntu/.ethereum/goerli/geth.ipc`` - Geth Node on Görli testnet running under user ``ubuntu`` (most probably that's what you need).


Show current WorkLock information
---------------------------------

You can obtain information about the current state of WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock status --network <NETWORK> --provider <YOUR PROVIDER URI>


If you want to see detailed information about your current bid, you can specify your bidder address with the ``--bidder-address`` flag:

.. code::

    (nucypher)$ nucypher worklock status --bidder-address <YOUR BIDDER ADDRESS> --network <NETWORK> --provider <YOUR PROVIDER URI>


Place a bid
-----------

You can place a bid to WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock bid --network <NETWORK> --provider <YOUR PROVIDER URI>


Recall that there's a minimum bid amount needed to participate in WorkLock.


Cancel a bid
------------

You can cancel a bid to WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock cancel-bid --network <NETWORK> --provider <YOUR PROVIDER URI>


Claim your stake
----------------

Once the claiming window is open, you can claim your tokens as a stake in NuCypher:

.. code::

    (nucypher)$ nucypher worklock claim --network <NETWORK> --provider <YOUR PROVIDER URI>


Once claimed, you can check that the stake was created successfully by running:

.. code::

    (nucypher)$ nucypher status stakers --staking-address <YOUR BIDDER ADDRESS> --network {network} --provider <YOUR PROVIDER URI>
    

Check remaining work
--------------------

If you have a stake created from WorkLock, you can check how much work is pending until you can get all your ETH locked in the WorkLock contract back:

.. code::

    (nucypher)$ nucypher worklock remaining-work --network <NETWORK> --provider <YOUR PROVIDER URI>


Refund locked ETH
-----------------

If you've committed some work, you are able to refund proportional part of ETH you've had bid in WorkLock contract:

.. code::

    (nucypher)$ nucypher worklock refund --network <NETWORK> --provider <YOUR PROVIDER URI>
