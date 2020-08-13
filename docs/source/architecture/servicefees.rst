.. _service-fees:

Service Fees (Pricing)
======================

Minimum Fee Rate
----------------

At network launch, stakers will choose a minimum fee rate, on a *per sharing policy* and *per 24h period basis*, that their worker machine (Ursula) will accept at the point of engagement with a network user (Alice). If Alice’s offer and deposit (contained alongside the sharing policy’s parameters in an ``Arrangement`` object broadcasted to the network), for a specified policy duration, computes as equal to or greater than the minimum fee rate, the sharing policy will be automatically accepted and Ursula’s access control service will commence. Ursula will service the sharing policy by being online and answering access requests, at that unchanging fee rate, until the specified expiration date or until an early revocation instigated by Alice.

The minimum fee rate is also calculated *per Ursula*. If Alice wishes to employ multiple Ursulas to service a single sharing policy (``n`` > 1), a common configuration, then they must pay each staker the same fee rate. Although Alices may attempt price optimization strategies to find the cheapest group of Ursula, they will nevertheless have to pay the highest rate from the set of minimum fee rates from the stakers with which they end up engaging.

Alices are required to escrow a deposit covering the cost of the entire duration of the policy, but fees are paid out to stakers once per period, after their Ursula confirms activity. Therefore the minimum sum of fees a staker will receive each period is the product of their specified minimum fee rate and the number of active sharing policies their Ursula has been assigned.
