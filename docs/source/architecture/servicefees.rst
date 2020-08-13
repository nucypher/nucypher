.. _service-fees:

Service Fees (Pricing)
======================

Minimum fee rate
----------------

At network launch, stakers will choose a minimum fee rate, on a *per sharing policy* and *per 24h period* basis, that their worker machine (Ursula) will accept at the point of engagement with a network user (Alice). If Alice’s offer and deposit (contained alongside the sharing policy’s parameters in an ``Arrangement`` object), for a specified policy duration, computes as equal to or greater than the minimum fee rate, the sharing policy will be automatically accepted and the access control service will commence. Ursula will service the sharing policy by being online and answering access requests, at that unchanging fee rate, until the specified expiration date or until an early revocation instigated by Alice.

The minimum fee rate is also calculated *per Ursula*. If Alice wishes to employ multiple Ursulas to service a single sharing policy (``n`` > 1), a common configuration, then they must pay each staker the same fee rate. Although Alices may attempt price optimization strategies to find the cheapest group of Ursula, they will nevertheless have to pay the highest rate from the set of minimum fee rates from the stakers with which they end up engaging.

Alices are required to escrow a deposit covering the cost of the entire duration of the policy, but fees are paid out to stakers once per period, after their Ursula confirms activity. Therefore the minimum sum of fees a staker will receive each period is the product of their specified minimum fee rate and the number of active sharing policies their Ursula has been assigned.


Global fee range
----------------

The global fee range is a means of establishing quasi-universal pricing for the NuCypher service. It is enforced via the function ``feeRateRange`` (in ``PolicyManager.sol``), which specifies constraints expressed in GWEI per sharing policy and per 24h period. The minimum fee rate rate chosen by stakers must fall within the global fee range. The network will launch with the following parameters:

**Minimum fee rate**

XX GWEI (~$X.XX x10^-X) *per period*

XX,XXX GWEI ($X.XXX) *per year*

**Maximum fee rate**

X,XXX GWEI (~$X.XX x10^-X) *per period*

XXX,XXX GWEI ($X.XXX) *per year*

**Default fee rate**

XXX GWEI (~$X.XX x10^-X) *per period*

XX,XXX GWEI ($X.XXXX) *per year*

1 GWEI = 10^-9 ETH
USD conversion utilizes the ETHUSD 100-day rolling average of 1 ETH = $222 (08.08.20)

Note that the minimum and maximum fee rate are an upper and lower bound to constrain the fee rate a staker may offer. The default fee rate is the rate that will be displayed and offered to Alices if the staker chooses not to configure this parameter themselves.

The fee range must be adhered to in identical fashion by all NuCypher stakers, regardless of their stake size or capacity. The fee range applies to all sharing policies, irrespective of the volume of re-encryption requests or other distinguishing attributes besides policy duration and the number of assigned Ursulas (``n``). It also applies equally to all periods in the future, until the moment that the global fee range’s parameters are adjusted or the range is removed, via official governance channels (see below). If a parameter update of this sort occurs, sharing policies that were previously established, but have not yet expired, should not have the per-period fee rate retroactively modified.

Setting a discretionary fee rate
--------------------------------

Stakers should use the ``setMinFeeRate`` function to specify the minimum fee rate that their Ursula (worker machine) will accept.

Note that Alices seeking to instantiate a new sharing policy are able to first discover all current minimum fee rates available to them, by retrieving the list of active stakers’ addresses, then querying the public variable ``PolicyManager.nodes(staker_address).minRewardRate`` with each ``staker_address``.

Setting a price point, even within a tight range, requires the evaluation and weighting of many factors against one another. Many of these considerations are unique to the staker, such as their ongoing operational costs, economy of scale (e.g. through participation in other networks) and participation timeframe. However, the most important factors to consider pertain to the holistic service from the perspective of network users – for example, the affordability, congruency, and stability, of all offered price points – i.e. how probable it is that prices remain affordable to a developer after they are irreversibly committed to integrating NuCypher access control into their application’s technology stack.

For an overview of price setting considerations, see the *Pricing Strategies* section of the Pricing Protocol & Economics paper.

Operational costs
-----------------

The cost of operating a typical Ursula, at network genesis, is estimated to be between $X and $Y per month. The variability of these estimates is driven primarily by diverse infrastructure costs across geographical locations, the range of feasible strategies for minimizing gas costs, and the economies of scale associated with service provision in multiple decentralized networks. This does not include the risks and opportunity costs of locking the Nu token for an extended duration of time. For a full derivation of overhead scenarios and the underlying assumptions, see the *Service-driven Pricing* section of the Pricing Protocol & Economics paper.


Note on staker sustainability
-----------------------------

Although the maximum fee rate parameter constrains the income from fees in one plane, it is a component of a strategy to maximize long-term network revenue through predictable, affordable and congruent pricing. Operational costs will almost certainly exceed fee income in the near-term, but the subsidy mechanism is designed to steadily support service-providers for the first 5 to 8 years – see *Demand uncertainty & fragility* section of the Staking & Economic Protocol paper for more detail. This stable source of income provides an extended window for the NuCypher community to trial various fee range parameters until a balance is struck between the extremes of 1) unaffordability for early customers leading to low demand, and 2) unsustainability for service-providers leading to low participation.

See the *Price point derivation* section, in particular the *Reconciling demand-side and service-side constraints* sub-section, of the Pricing Protocol & Economics paper for a deeper analysis of this trade-off.