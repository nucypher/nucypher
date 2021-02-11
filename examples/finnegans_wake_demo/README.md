# Ursula exchange example over local network

This illustrates Alice sharing data with Bob over the NuCypher network using proxy re-encryption,
without revealing private keys to intermediary entities.

1. Alice sets a Policy on the NuCypher network (2/3) and grants access to Bob
2. Label and Alice's public key provided to Bob
4. Bob joins the policy by Label and Alice's public key
5. Enrico created for the policy 
6. Each plaintext message gets encapsulated through the Enrico to messageKit
5. Bob receives and reconstructs the Enrico from Policy public key and Enrico public key
6. Bob retrieves the original message from Enrico and MessageKit


### Run a fleet of federated Ursulas
`python ../run_demo_ursula_fleet.py`


### Run
`python finnegans-wake-demo.py`
