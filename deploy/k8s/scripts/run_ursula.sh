#! /bin/bash

# our local ip address
export MY_IP=$(wget -q -O - ifconfig.me);

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

if [ ! -e "$ROOT_DIR/nucypher/ursula.config" ]
then
  # tar the newly created config
  nucypher --debug ursula init --provider-uri $NUCYPHER_PROVIDER_URI --network $NUCYPHER_NETWORK --checksum-address $ACCOUNT_ADDRESS --force
  tar -C $ROOT_DIR -zcvf $ROOT_DIR/$ACCOUNT_ADDRESS@$MY_IP.tar.gz $ROOT_DIR/nucypher
  # and send it to S3
  python /code/deploy/k8s/scripts/publish_config.py
else
  sleep 5
fi

set -e  # crash on error

# now wait for blockchain to sync
python /code/deploy/k8s/scripts/wait_for_sync.py
echo "\nlocal blockchain is synced. ready to check funding."


# check if our address has the needed Eth and NU for staking
python /code/deploy/k8s/scripts/check_for_funds.py
echo "\nwe have funds.  ready to stake."

# go ahead and stake
nucypher --debug ursula stake --value 15001 --duration 365 --poa --force

nucypher --debug ursula run --checksum-address $ACCOUNT_ADDRESS --force
sleep 10000  # so you can shell in after everything doesn't work


