# Ursula exchange example over live network

This is an illustration of NuCypher Decentralized Key Management System (KMS) allowing Alice to share a 
data with Bob using proxy re-encryption paradigm. This enables the private sharing of data between 
participants in public consensus networks, without revealing data keys to intermediary entities.

1. Alice sets a Policy on the NuCypher network (2/3) and grants access to Bob
2. Label and Alice's key public key provided to Bob
4. Bob joins the policy by Label and Alice's public key
5. Enrico created for the policy 
6. Each plaintext message gets encapsulated through the Enrico to messageKit
5. Bob receives and reconstructs the Enrico from Policy public key and Enrico public key
6. Bob retrieves the original message form Enrico and MessageKit

### Install Nucypher
```
git clone https://github.com/nucypher/nucypher.git  # clone NuCypher repository
cd nucypher
git checkout federated  # We need a federated branch which isn't using blockchain
pipenv install --dev --three --skip-lock --pre
pipenv shell
```

### Download the Book!
`./download_finnegans_wake.sh` 


### Run
`python3 finnegans-wake-concise-demo.py`
