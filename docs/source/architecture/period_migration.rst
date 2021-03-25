Period Migration
================

In the NuCypher Network, a *Period* is the minimum unit for policy duration, and also corresponds to the frequency that
Workers must make an on-chain commitment to being online and available; periods begin at UTC midnight.

Genesis
-------

At the Network launch (genesis) on October 15th, 2020, the length of a period was 24 hours. As a result, before
UTC midnight, Workers needed to make a per period (daily) on-chain commitment transactions indicating availability for
the following period (after UTC midnight).

The cost of the commitment transaction was approximately 200k gas, but could cost more depending on the number of
sub-stakes being staked. Given the significant increase in Ethereum gas since launch, the cost of the daily
commitment transaction significantly increased and became untenable. Particularly for stake sizes closer to the minimum
stake size, the NU staking rewards and fees received from running a Worker may not cover the cost of this commitment
transaction.

Reducing the transaction gas cost was a necessity, and there were multiple mitigation attempts:

#. Removal of inactive sub-stakes i.e. sub-stakes that expired and were no longer relevant (`PR #2384 <https://github.com/nucypher/nucypher/issues/2384>`_).
#. Addition of a Worker configuration setting to specify a highest gas price that Workers were willing to pay for the
   commitment transaction. Commitment attempts are made throughout the current period, and if the gas price at the time
   is too high, the commitment is not made (`PR #2445 <https://github.com/nucypher/nucypher/issues/2445>`_).

Ultimately these were incremental solutions, which worked around the underlying issue. A more comprehensive next step
was to increase the period length i.e. reduce the frequency with which Workers needed to make the on-chain commitment
transaction, thereby reducing the cost by a factor based on the increase in period length.

Taking a long-term perspective, lowering Worker overhead encourages more Stakers and Worker, and enables more
competitive break-even policy fee price points for network usage which is likely to increase user adoption.


7-Day Period
------------

.. TODO update date and add link to approval

A `proposal to increase the network period length <https://dao.nucypher.com/t/1-improve-staker-p-l-by-increasing-period-duration/110>`_,
outlining the pros and cons, was put forth to the :doc:`NuCypher DAO </architecture/dao>`; 7 days received the majority of votes.
On ``[some date]`` the NuCypher DAO approved the period migration, and subsequently, the period length for the NuCypher Network.

Modifying the period length to 7 days involved changes to to the ``StakingEscrow`` smart contract, and the economics
settings for the network. This change is purely for reducing the frequency of commitment transactions, and does not
affect the total staking rewards received by a Staker for running a Worker. However, since payouts to Stakers are
made after periods are completed, instead of waiting 24 hours, Stakers will need to wait 7 days - but the value
received will be 7 days worth.


.. TODO need a blurb about automatic migration, possible manual migration, and expectations after initial migration


.. important::

    It is entirely possible that the NuCypher DAO decides to update the period length again in the future.
