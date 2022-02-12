# Finnegan's Wake Demo

This illustrates Alice sharing data with Bob over the NuCypher network using proxy re-encryption,
without revealing private keys to intermediary entities.

1. Alice sets a Policy on the NuCypher network (2/3) and grants access to Bob
2. Label and Alice's public key provided to Bob
4. Bob joins the policy by Label and Alice's public key
5. Enrico created for the policy 
6. Each plaintext message gets encapsulated through the Enrico to messageKit
5. Bob receives and reconstructs the Enrico from Policy public key and Enrico public key
6. Bob retrieves the original message from Enrico and MessageKit

There are two version of the example, one federated example using a local network
and another example using the nucypher application development tesnet: Lynx.

### Federated Demo

First run the local federated network:
`python ../run_demo_ursula_fleet.py`

Then run the demo:
`python finnegans-wake-demo-federated.py`

### Testnet Demo

First, configure the demo.  Be sure tat alice's address has some Goerli ETH.
```bash
export DEMO_ETH_PROVIDER_URI=<GOERLI RPC ENDPOINT>
export DEMO_ALICE_ETH_ADDRESS=<ETH ADDRESS>
export DEMO_SIGNER_URI=keystore://<PATH TO KEYSTORE>
```

Then run the demo:
`python finnegans-wake-demo-testnet.py`
