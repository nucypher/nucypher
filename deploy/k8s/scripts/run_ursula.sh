#! /bin/bash

# set -e


# 1st wait for the geth container to start up and create an account
while [ ! -s "$ROOT_DIR/address.txt" ]
do
  echo "waiting for geth account creation"
  sleep 1
done

# get the address of the account created by geth
export ACCOUNT_ADDRESS=`cat $ROOT_DIR/address.txt`;

while [ ! -e "$ROOT_DIR/geth/geth.ipc" ]
do
  echo "waiting for geth startup"
  sleep 1
done
sleep 2

# and our ip address
export MY_IP=$(wget -q -O - ifconfig.me);

nucypher --debug ursula init --provider-uri $NUCYPHER_PROVIDER_URI --network $NUCYPHER_NETWORK --checksum-address $ACCOUNT_ADDRESS --force

# tar the newly created config
tar -C $ROOT_DIR -zcvf $ROOT_DIR/$ACCOUNT_ADDRESS@$MY_IP.tar.gz $ROOT_DIR/nucypher

# and send it to S3
python /code/deploy/k8s/scripts/publish_config.py

nucypher --debug ursula stake --value 15001 --duration 365 --poa --force

nucypher --debug ursula run --checksum-address $ACCOUNT_ADDRESS --force
sleep 10000  # so you can shell in after everything doesn't work


