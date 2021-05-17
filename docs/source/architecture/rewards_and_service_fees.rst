.. _service-fees:

************************
Rewards and Service Fees
************************

Token Rewards
=============

The NuCypher network is an example of a decentralized service marketplace,
providing infrastructural services to digital applications/systems (‘users’)
via a distributed array of independent node operators (‘service-providers’).
NuCypher’s primary offerings depend, to some extent, on long-term commitment
to the network by a large, diversified population of service-providers.

Like many decentralized and centralized service marketplaces,
an abundance of reliable, committed service-providers is critical
– and that the network establishes this state prior to the emergence of
user adoption, lest the adoption be short-lived. As with any network,
operating a node incurs various overheads, upfront and ongoing, and denominated
in fiat, cryptocurrency and time. Moreover, eligibility for service provision in
the NuCypher network is contingent on the acquisition and time-locking of
collateral (‘staking’), which burdens the service-provider with ongoing risk
and opportunity cost. NuCypher users, who require the collateral of those serving
them to remain locked for at least as long as their commercial engagement with
the network – engagements which in some cases will last for months or years
– protract this burden.

If demand for NuCypher services rises sufficiently, direct payments from users
(‘fees’) will sustain the operations of service-providers. However,
before demand reaches this threshold, another stream of revenue is required
to incentivize a sufficient number of service-providers to join the network,
and to subsidize the cost of their operations until a mature fee market
materializes. Thus, an important mechanism in the NuCypher protocol is the
distribution of subsidies to actively staking service-providers,
realized through the growth of the native token’s circulating supply.

Sub-stakes
----------

In order to be eligible to answer user requests, earn fees, and receive subsidies,
a service-provider must commit to servicing the network for some period of
time by locking collateral (staking). Service-providers specify a stake
unlocking time in the future :math:`t_u`,
where at time :math:`t` the minimum duration :math:`t_u − t` may not be fewer than
:math:`D_{min} = 4` (measured in periods, with 1 period equals 7 days),
but may be any greater number of periods.

The NuCypher protocol allows service-providers to partition their stake into
sub-stakes, up to a maximum of 30.
A sub-stake has a unique remaining duration :math:`D` – the number of periods until
it unlocks and the tokens become freely withdrawable. The sub-stake size :math:`\ell`
is the number of tokens locked. It is possible to extend (but not reduce)
:math:`D` for a sub-stake, or split a sub-stake by extending :math:`D` for part of it.
It is also possible to acquire more tokens and increase :math:`\ell` in any sub-stake.
This mechanism enables more granular planning for future liquidity needs.
See :ref:`stake-management` for a more complete guide of the operations that
can be performed over sub-stakes.

Subsidy coefficient
-------------------

The amount of rewards earned by each sub-stake :math:`i` is proportional to
the duration of time until it unlocks (:math:`D_i = t_i − t`),
and the number of tokens in the sub-stake :math:`\ell_i`. This proportion is represented
by a `subsidy coefficient` (:math:`\kappa`, or `kappa`) which ranges from 0.5 to 1.
Sub-stakes that unlock in 52 periods (approximately 1 year) or more
receive the maximum subsidy (:math:`\kappa = 1`), whereas a sub-stake that unlocks in
4 periods (28 days) would receive slightly over half the maximum subsidy (:math:`\kappa \approx 0.54`).
The subsidy coefficient :math:`\kappa` for a given sub-stake :math:`i` is calculated
as following, where :math:`D_{max}` is currently set to 52 periods (364 days):

.. math::
    \kappa_i = 0.5 \cdot \left(1 + \frac{\mathsf{min}(D_i, D_{max})}{D_{max}} \right)


To improve user experience, instead of this coefficient,
in NuCypher's user interfaces we display an equivalent representation called
"`boost`", a value ranging between 1 and 2,
and defined as :math:`\text{boost} = \frac{\kappa}{0.5}`.


.. code:: bash

    ╒═══════╤══════════╤═════════════╤═════════════╤═══════════════╤════════╤═══════════╕
    │  Slot │ Value    │   Remaining │ Enactment   │ Termination   │  Boost │ Status    │
    ╞═══════╪══════════╪═════════════╪═════════════╪═══════════════╪════════╪═══════════╡
    │     0 │ 45000 NU │           5 │ Mar 24 2021 │ Apr 21 2021   │  1.10x │ DIVISIBLE │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛


Subsidies calculation
---------------------

For a given period, a sub-stake :math:`i` of size :math:`\ell_i` will receive
the following subsidy :math:`s_i`, where :math:`L` is the sum of all locked
sub-stakes (for all active stakers in the network) and :math:`I_{max}`
is the maximum number of tokens that can be minted per period:

.. math::
    s_i = \kappa_i \cdot \frac{\ell_i}{L} \cdot I_{max}

Note that current value for :math:`I_{max}` is 7,017,566.35 NU.
See the `Staking Protocol & Economics paper <https://github.com/nucypher/whitepaper/raw/master/economics/staking_protocol/NuCypher_Staking_Protocol_Economics.pdf>`_
for more details on subsidies calculation.



Service Fees (Pricing)
======================

.. _paper: https://github.com/nucypher/whitepaper/blob/master/economics/pricing_protocol/NuCypher_Network__Pricing_Protocol_Economics.pdf
.. _forum: https://dao.nucypher.com/t/welcome-to-the-dao-forum/29
.. _whitepaper: https://github.com/nucypher/whitepaper/blob/master/economics/staking_protocol/NuCypher_Staking_Protocol_Economics.pdf
.. _enacted: https://client.aragon.org/#/nucypherdao/0xc0a7249bb3f41f8f611149c23a054810bde06f49/vote/1/
.. _ERT: https://dao.nucypher.com/t/emergency-response-team/28/2

Minimum fee rate
----------------

When stakers join the network, they specify a minimum fee rate, on a *per sharing policy* and *per period (7 days)* basis, that their worker (Ursula) will accept at the point of engagement with a network user (Alice). If Alice’s offered per period rate (contained alongside the sharing policy’s parameters in an ``Arrangement`` object) for a specified policy duration computes as equal to or greater than the minimum fee rate, the sharing policy will be accepted by Ursula and the access control service will commence. Ursula will service the sharing policy by being online and answering access requests, at that unchanging per period fee rate, until the specified expiration date or an early revocation is instigated by Alice.

The minimum fee rate applies to each individual worker machine managing a given sharing policy. In other words, the rate is also *per Ursula*. If Alice wishes to employ multiple Ursulas to service a single sharing policy (``n`` > 1), a common configuration, then they must pay each staker associated with that policy the same fee rate. This rate will be the highest from the set of *minimum* fee rates specified by the stakers with which they engage. Alices may attempt price optimization strategies to find the cheapest group of Ursulas.

When issuing a sharing policy, Alices are required to escrow a deposit covering the cost of the entire duration of the policy. This deposit is split and paid out in tranches to stakers once per period. The precise payment flow follows a repeated three-period cycle; in the first period the Ursula *makes a commitment* to the second period. Then, the Ursula services the policy during the second period (and makes a commitment to the third period). In the third period, they receive the fee tranche for their work during the second period, and continue servicing the policy, etc. This cycle continues until all the policies that Ursula is responsible for have expired. Note that *making a commitment* was formerly referred to as *confirming activity*.

The minimum sum of fees a staker can receive period-to-period is the product of their specified minimum fee rate and the number of active sharing policies their Ursula has been assigned.


Global fee range
----------------

The global fee range is a means of establishing quasi-universal pricing for the NuCypher service. It is enforced via the function ``feeRateRange`` in ``PolicyManager.sol``, which specifies per sharing policy and per period (7 days) constraints expressed in **WEI**. Note that elsewhere, fee rates are discussed in **GWEI** and fiat (USD).

The minimum fee rate chosen by stakers must fall within the global fee range. The network will launch with the following parameters:

**Minimum fee rate**

350 GWEI *per period, per policy, per Ursula*

**Maximum fee rate**

3500 GWEI *per period, per policy, per Ursula*

**Default fee rate**

350 GWEI *per period, per policy, per Ursula*

The minimum and maximum fee rate are a lower and upper bound to constrain the fee rate a staker may offer. The default fee rate is the rate that will be displayed and offered to Alices if the staker chooses not to configure this parameter themselves, or chooses a rate outside the boundaries of the global fee range. The default rate will also be used if the range's boundaries are updated, a staker's specified rate *now* falls outside the range, and they fail to change it.

The fee range must be adhered to in identical fashion by all NuCypher stakers, regardless of their stake size or capacity. The fee range applies to all sharing policies, irrespective of the volume of re-encryption requests or other distinguishing attributes. It also applies equally to all periods in the future, until the moment that the global fee range’s parameters are adjusted or the range is removed, via official governance processes (see below). If an update of this sort occurs, sharing policies that were previously established, but have not yet expired, should not have the per-period fee rate retroactively modified. Note that the global fee range is only applicable to stakers and Ursulas. Alices are free to pay as high a rate as they like.


Governance & pricing paper
---------------------------------------

In order to successfully interact with the ``PolicyManager.sol`` contract, the global fee range must be adhered to by the Ursula (and Alice). Failing this, the contract will throw up an error and it will not be possible to commence a commercial engagement or pay/receive fees. Attempts to circumvent NuCypher’s smart contracts are likely to be futile given the requirement of coordinated modification and redeployment by network users and a critical mass of other stakers.

Given its high enforceability, the presence of an inflexible fee range dictating the bounds of every transaction is arguably the most critical component of the NuCypher protocol’s economic design and parametrization, particularly over the long-term and with respect to the sustainability of the network. From a governance perspective, it is also amongst the most malleable, thanks in part to the ``setFeeRateRange`` utility. If a quorum of stakers wish to set prices outside the range, then they have the right to lobby and propose a widening of the global fee range, its removal altogether, or some other design modification (e.g. narrowing the range). They may do so via the NuCypher DAO – the owner of all NuCypher smart contracts - by submitting a proposal to be validated by stakers, weighted in proportion to their stake size. See the DAO forum_ for guidance on the NuCypher DAO and governance processes and pipelines.

The Pricing Protocol & Economics paper_ serves as a resource for community debate, proposals for modification, and DAO-driven upgrades/redeployments in the future. The paper discusses the merits and risks of quasi-universal pricing and the enforcement of an upper and lower bound on all offered price points. It introduces a price point analysis from a demand-side, service-side and theoretical standpoint to produce the provisional constraints in absolute terms that the network will launch with (above).

.. note::

    This Pricing Protocol & Economics paper was originally written when period lengths were 24 hours; period lengths are now 7 days but the core principles still apply.


Setting a discretionary fee rate
--------------------------------

Stakers should use the ``setMinFeeRate`` function to specify the minimum fee rate that their Ursula (worker machine) will accept. Note that Alices seeking to instantiate new sharing policies are able to first discover all current minimum fee rates available to them, by retrieving the list of active stakers’ addresses, then querying the public variable ``PolicyManager.getMinFeeRate(staker_address)`` with each ``staker_address``.

Setting a price point, even within a tight range, requires the evaluation and weighting of many factors against one another. Many of these considerations are unique to the staker, such as their ongoing operational costs, economy of scale (e.g. through participation in other networks) and participation timeframe. However, the most important factors to consider pertain to the holistic service from the perspective of network users – for example, the affordability, congruency, and stability, of all offered price points – in other words, how probable it is that prices remain affordable to a developer after they are irreversibly committed to integrating NuCypher access control into their application’s technology stack. For more on price setting considerations, see the *Pricing Strategies* section of the Pricing Protocol & Economics paper_.


Note on staker sustainability
-----------------------------

Although the maximum fee rate parameter constrains the income from fees in one plane, it is a component of a strategy to maximize long-term network revenue through predictable, affordable and congruent pricing. Operational costs will almost certainly exceed fee income in the near-term, but the subsidy mechanism is designed to steadily support service-providers for the first 5 to 8 years – see the *Demand uncertainty & fragility* section of the Staking & Economic Protocol whitepaper_ for more detail. This subsidy provides an extended window for the NuCypher community to trial various fee range parameters until a balance is struck between the extremes of 1) unaffordability for early customers leading to low demand, and 2) unsustainability for service-providers leading to low participation. See the *Reconciling demand-side and service-side constraints* section of the Pricing Protocol & Economics paper_ for an analysis of this trade-off.
