Demo of granting permission and retrieving
============================================

Init Alice and Bob
---------------------
> nucypher alice init --provider ipc:///home/ubuntu/.ethereum/goerli/geth.ipc  --poa
> nucypher bob init --provider ipc:///home/ubuntu/.ethereum/goerli/geth.ipc

Get Bob's public keys
------------------------
> nucypher bob public-keys

Alice grants
--------------
> nucypher alice grant \
>     --teacher 13.53.75.91:9151 \
>     --bob-verifying-key ... \
>     --bob-encrypting-key ... \
>     --label asdf \
>     --expiration 2019-12-11T10:07:50Z \
>     --m 1 --n 1 --value 1 --debug

Enrico encrypts
------------------
> nucypher enrico encrypt \
>     --policy-encrypting-key ... \
>     --message "Llama's ass"

Bob retrieves
---------------
> nucypher bob retrieve \
>     --label asdf \
>     --message-kit ... \
>     --policy-encrypting-key ... \
>     --alice-verifying-key ... \
>     --teacher 13.53.75.91:9151

cleartexts ...... ['TGxhbWEncyBhc3M=']

> python
> import base64
> base64.b64decode('TGxhbWEncyBhc3M=')
b"Llama's ass"
