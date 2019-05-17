#!/bin/sh

args="$@"
echo $GETH_PW > file.txt
echo "running geth account new with $args"
geth $args --password file.txt account new | grep "Public address of the key:" | awk 'NF>1{print $NF}' > $ROOT_DIR/address.txt
rm file.txt
echo "running geth with $args"
geth $args
