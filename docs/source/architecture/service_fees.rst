.. _service-fees:

Service Fees (Pricing)
======================

.. _paper: https://github.com/nucypher/whitepaper/blob/master/economics/pricing_protocol/NuCypher_Network__Pricing_Protocol_Economics.pdf
.. _forum: https://dao.nucypher.com/t/welcome-to-the-dao-forum/29
.. _whitepaper: https://github.com/nucypher/whitepaper/blob/master/economics/staking_protocol/NuCypher_Staking_Protocol_Economics.pdf
.. _enacted: https://client.aragon.org/#/nucypherdao/0xc0a7249bb3f41f8f611149c23a054810bde06f49/vote/1/
.. _ERT: https://dao.nucypher.com/t/emergency-response-team/28/2

Minimum fee rate
----------------

When stakers join the network, they specify a minimum fee rate, on a *per sharing policy* and *per 24h period* basis, that their worker (Ursula) will accept at the point of engagement with a network user (Alice). If Alice’s offered per period rate (contained alongside the sharing policy’s parameters in an ``Arrangement`` object) for a specified policy duration computes as equal to or greater than the minimum fee rate, the sharing policy will be accepted by Ursula and the access control service will commence. Ursula will service the sharing policy by being online and answering access requests, at that unchanging per period fee rate, until the specified expiration date or an early revocation is instigated by Alice.

The minimum fee rate applies to each individual worker machine managing a given sharing policy. In other words, the rate is also *per Ursula*. If Alice wishes to employ multiple Ursulas to service a single sharing policy (``n`` > 1), a common configuration, then they must pay each staker associated with that policy the same fee rate. This rate will be the highest from the set of *minimum* fee rates specified by the stakers with which they engage. Alices may attempt price optimization strategies to find the cheapest group of Ursulas.

When issuing a sharing policy, Alices are required to escrow a deposit covering the cost of the entire duration of the policy. This deposit is split and paid out in tranches to stakers once per period. The precise payment flow follows a repeated three-period cycle; in the first period the Ursula *makes a commitment* to the second period. Then, the Ursula services the policy during the second period (and makes a commitment to the third period). In the third period, they receive the fee tranche for their work during the second period, and continue servicing the policy, etc. This cycle continues until all the policies that Ursula is responsible for have expired. Note that *making a commitment* was formerly referred to as *confirming activity*.

The minimum sum of fees a staker can receive period-to-period is the product of their specified minimum fee rate and the number of active sharing policies their Ursula has been assigned.


Global fee range
----------------

The global fee range is a means of establishing quasi-universal pricing for the NuCypher service. It is enforced via the function ``feeRateRange`` in ``PolicyManager.sol``, which specifies per sharing policy and per 24h period constraints expressed in **WEI**. Note that elsewhere, fee rates are discussed in **GWEI** and fiat (USD).

The minimum fee rate chosen by stakers must fall within the global fee range. The network will launch with the following parameters:

**Minimum fee rate**

50 GWEI *per period, per policy, per Ursula*

**Maximum fee rate**

500 GWEI *per period, per policy, per Ursula*

**Default fee rate**

50 GWEI *per period, per policy, per Ursula*

The minimum and maximum fee rate are a lower and upper bound to constrain the fee rate a staker may offer. The default fee rate is the rate that will be displayed and offered to Alices if the staker chooses not to configure this parameter themselves, or chooses a rate outside the boundaries of the global fee range. The default rate will also be used if the range's boundaries are updated, a staker's specified rate *now* falls outside the range, and they fail to change it.

The fee range must be adhered to in identical fashion by all NuCypher stakers, regardless of their stake size or capacity. The fee range applies to all sharing policies, irrespective of the volume of re-encryption requests or other distinguishing attributes. It also applies equally to all periods in the future, until the moment that the global fee range’s parameters are adjusted or the range is removed, via official governance processes (see below). If an update of this sort occurs, sharing policies that were previously established, but have not yet expired, should not have the per-period fee rate retroactively modified. Note that the global fee range is only applicable to stakers and Ursulas. Alices are free to pay as high a rate as they like.

The genesis parameters for the global fee range (above) were enacted_ and deployed by the NuCypher DAO's ERT_ on October 14th 2020, using the ``setFeeRateRange`` utility contained in the contract ``PolicyManager.sol``.

Governance & pricing paper
---------------------------------------

In order to successfully interact with the ``PolicyManager.sol`` contract, the global fee range must be adhered to by the Ursula (and Alice). Failing this, the contract will throw up an error and it will not be possible to commence a commercial engagement or pay/receive fees. Attempts to circumvent NuCypher’s smart contracts are likely to be futile given the requirement of coordinated modification and redeployment by network users and a critical mass of other stakers.

Given its high enforceability, the presence of an inflexible fee range dictating the bounds of every transaction is arguably the most critical component of the NuCypher protocol’s economic design and parametrization, particularly over the long-term and with respect to the sustainability of the network. From a governance perspective, it is also amongst the most malleable, thanks in part to the ``setFeeRateRange`` utility. If a quorum of stakers wish to set prices outside the range, then they have the right to lobby and propose a widening of the global fee range, its removal altogether, or some other design modification (e.g. narrowing the range). They may do so via the NuCypher DAO – the owner of all NuCypher smart contracts - by submitting a proposal to be validated by stakers, weighted in proportion to their stake size. See the DAO forum_ for guidance on the NuCypher DAO and governance processes and pipelines.

The Pricing Protocol & Economics paper_ serves as a resource for community debate, proposals for modification, and DAO-driven upgrades/redeployments in the future. The paper discusses the merits and risks of quasi-universal pricing and the enforcement of an upper and lower bound on all offered price points. It introduces a price point analysis from a demand-side, service-side and theoretical standpoint to produce the provisional constraints in absolute terms that the network will launch with (above).


Setting a discretionary fee rate
--------------------------------

Stakers should use the ``setMinFeeRate`` function to specify the minimum fee rate that their Ursula (worker machine) will accept. Note that Alices seeking to instantiate new sharing policies are able to first discover all current minimum fee rates available to them, by retrieving the list of active stakers’ addresses, then querying the public variable ``PolicyManager.getMinFeeRate(staker_address)`` with each ``staker_address``.

Setting a price point, even within a tight range, requires the evaluation and weighting of many factors against one another. Many of these considerations are unique to the staker, such as their ongoing operational costs, economy of scale (e.g. through participation in other networks) and participation timeframe. However, the most important factors to consider pertain to the holistic service from the perspective of network users – for example, the affordability, congruency, and stability, of all offered price points – in other words, how probable it is that prices remain affordable to a developer after they are irreversibly committed to integrating NuCypher access control into their application’s technology stack. For more on price setting considerations, see the *Pricing Strategies* section of the Pricing Protocol & Economics paper_.


Note on staker sustainability
-----------------------------

Although the maximum fee rate parameter constrains the income from fees in one plane, it is a component of a strategy to maximize long-term network revenue through predictable, affordable and congruent pricing. Operational costs will almost certainly exceed fee income in the near-term, but the subsidy mechanism is designed to steadily support service-providers for the first 5 to 8 years – see the *Demand uncertainty & fragility* section of the Staking & Economic Protocol whitepaper_ for more detail. This subsidy provides an extended window for the NuCypher community to trial various fee range parameters until a balance is struck between the extremes of 1) unaffordability for early customers leading to low demand, and 2) unsustainability for service-providers leading to low participation. See the *Reconciling demand-side and service-side constraints* section of the Pricing Protocol & Economics paper_ for an analysis of this trade-off.
