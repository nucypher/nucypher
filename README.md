# Ursula exchange example over live network
This is an illustration of NuCypher Decentralized Key Management System (KMS) allowing Alice to share a 
data with Bob using proxy re-encryption paradigm. This enables the private sharing of data between 
participants in public consensus networks, without revealing data keys to intermediary entities.

1. Alice sets a Policy on the NuCypher network (2/3) and grants access to Bob
2. Label and Alice's key public key provided to Bob
4. Bob joins the policy by Label and Alice's public key
5. DataSource created for the policy 
6. Each plaintext message gets encapsulated through the DataSource to messageKit
5. Bob receives and reconstructs the DataSource from Policy public key and DataSource public key
6. Bob retrieves the original message form DataSource and MessageKit

## Install and prepare
```
git clone https://github.com/nucypher/nucypher.git  # clone NuCypher repository
cd nucypher
git checkout federated  # We need a federated branch which isn't using blockchain
pipenv install --dev --three --skip-lock
pipenv shell
pip3 install -e .
# ok, now you have nucypher installed in virtual environment

# prepare to run several nodes locally
cd examples
mkdir examples-runtime-cruft
```
## Run
```
# run the following in several terminals
python3 run_federated_ursula.py 3500  # <- seed node
python3 run_federated_ursula.py 3501 3500
python3 run_federated_ursula.py 3502 3500

# now get some text to re-encrypt and run the demo
wget https://www.gutenberg.org/files/2701/old/moby10b.txt
python3 finnegans-wake-federated.py moby10b.txt 3501
```