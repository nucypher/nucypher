#!/bin/sh

args="$@"
if [ ! -s "$ROOT_DIR/address.txt" ]
then
    echo "running geth account new with $args"
    echo $GETH_PW > file.txt
    geth $args --password file.txt account new | grep "Public address of the key:" | awk 'NF>1{print $NF}' > $ROOT_DIR/address.txt
    rm file.txt
fi
echo "running geth with $args"
geth $args
