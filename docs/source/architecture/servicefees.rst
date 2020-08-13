.. _service-fees:

Service Fees (Pricing)
======================

Minimum Fee Rate
----------------

At network launch, stakers will choose a minimum fee rate, on a *per sharing policy* and *per 24h period basis*, that their worker machine (Ursula) will accept at the point of engagement with a network user (Alice). If Alice’s offer and deposit (contained alongside the sharing policy’s parameters in an ``Arrangement`` object broadcasted to the network), for a specified policy duration, computes as equal to or greater than the minimum fee rate, the sharing policy will be automatically accepted and Ursula’s access control service will commence. Ursula will service the sharing policy by being online and answering access requests, at that unchanging fee rate, until the specified expiration date or until an early revocation instigated by Alice.

The minimum fee rate is also calculated *per Ursula*. If Alice wishes to employ multiple Ursulas to service a single sharing policy (``n`` > 1), a common configuration, then they must pay each staker the same fee rate. Although Alices may attempt price optimization strategies to find the cheapest group of Ursula, they will nevertheless have to pay the highest rate from the set of minimum fee rates from the stakers with which they end up engaging.

Alices are required to escrow a deposit covering the cost of the entire duration of the policy, but fees are paid out to stakers once per period, after their Ursula confirms activity. Therefore the minimum sum of fees a staker will receive each period is the product of their specified minimum fee rate and the number of active sharing policies their Ursula has been assigned.


Global Fee Range
----------------

The global fee range is a means of establishing quasi-universal pricing for the NuCypher access control service in the early eras of the network’s existence. It is enforced via the function ``feeRateRange`` (in ``PolicyManager.sol``), which specifies parameters expressed in GWEI per 24h period.

The minimum fee rate rate chosen by the staker must fall within the global fee range. The network will launch with the following fee constraints for each sharing policy:

**Minimum fee rate**

XX GWEI (~$X.XX x10^-X) per period

XX,XXX GWEI ($X.XXX) per year

**Maximum fee rate**

X,XXX GWEI (~$X.XX x10^-X) per period

XXX,XXX GWEI ($X.XXX) per year

**Default fee rate**

XXX GWEI (~$X.XX x10^-X) per period

XX,XXX GWEI ($X.XXXX) per year

1 GWEI = 10^-9 ETH
USD conversion utilizes the ETHUSD 100-day rolling average of 1 ETH = $222 (08.08.20)

Note that the minimum and maximum fee rate are an upper and lower bound to constrain the fee rate a staker may offer. The default fee rate is the rate that will be displayed and offered to Alices if the staker chooses not to configure this parameter themselves.

The fee range must be adhered to in identical fashion by all NuCypher stakers, regardless of their stake size or capacity. The fee range applies to all sharing policies, irrespective of the volume of re-encryption requests or other distinguishing attributes besides policy duration and the number of assigned Ursulas (``n``). It also applies equally to all periods in the future, until the moment that the global fee range’s parameters are adjusted or the range is removed, via official governance channels (NuCypher DAO). If a parameter update of this sort occurs, sharing policies that were previously established (but have not yet expired) should not have the per-period fee rate retroactively modified.

