==================
Retrieving Secrets
==================

One node in your distributed application has already created a Policy and Granted access using Alice.  Another node has shared several secrets on that Policy using Enrico.  Now, you're ready to retrieve a secret using Bob and use the secret in your dapp.

<<<<<<< HEAD
We sometimes jokingly refer to Bob as "Bob the BUIDLer" - but there is at least a small nugget of truth in this designatation.  A critical design decision about user-facing functionality in any NuCypher-powered decentralized application is where, when, and how to use the secrets that you retrieve using the network.

It's not an exaggeration to say that the parameters you pass to `retrieve(...)` are a representation of the critique your application is making in the world.
=======
>>>>>>> d14ca288... Temporary.

Bob's Adventure
---------------

<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 4c9081b4... Temporary 2.
The Capsule finally Activated, Bob's face reflected its gold glow.  All he needed to do now was to slide his private keycard across its slot to open it and finally have The Secret inside.

----

24 hours earlier, Bob had been sitting in the Pogo Lounge of the Beverly Heights Hotel (of course), when a call came from Alice: Bob had been Granted access.  And Enrico had shared a Capsule with Bob.

On the advice of his Teacher Node, Bob rented a fast car with no top, and set out to find a cohort of *five specific* Ursulas - none of whom had ever even met one another.  In truth, Bob really only needed to convene with *any three* of these Ursulas for his gonzo journey to be complete.

He needed to bring this Capsule around to each Ursula, who, upon inspecting it (but not being able to peer inside), were prepared to give him a CFrag to plug into one of the `n` slots on the Capsule.

As soon as Bob completed plugging any `m` of these CFrags in, the Capsule glowed its sunny glow to show that it was ready for Bob's key; the final piece of the process of retrieve().


Basic retrieval
---------------

Alice has created a Policy and Granted Bob access.
Enrico has given Bob a Capsule.

Now Bob wants the message.

<<<<<<< HEAD

=======
From seat 33K (coach obviously) of his hastily booked flight aboard an aging four-engine jumbo jet, Bob kept a sharp eye on the overhead compartment across the aisle where he has carefully placed it: the Capsule.

He knew his quest well - he had gone over and over it in his mind and in his test suite.  He needed to find a worldwide cohort of five Ursulas - none of whom had ever even met one another.  Well, to be more specific, he needed to convene with any three of them.
>>>>>>> d14ca288... Temporary.
=======

>>>>>>> 4c9081b4... Temporary 2.


The question of whether to preserve or discard saved CFrags and activated Capsules
----------------------------------------------------------------------------------

After retrieving a secret, Bob can opt to either retain the reencrypted CFrags (and thus continuing to have access to the secret without needing to use the network again) or to delete them.

The advantages of retaining the secret are obvious: Bob no longer needs to make the `m` connections on the network needed to retrieve it.

However, a Bob may wish to immediately discard the secret in order to reduce its attack surface in the event that it is compromised.  In the "key management" use case, each Bob typically wants to custody keys for as short a time as possible.

**It is sensible for your threat model to *always* assume that an attacker will retain access to secrets, despite your chosen settings.**






