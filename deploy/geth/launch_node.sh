#!/usr/bin/env bash

IP="127.0.0.1"

geth --datadir ./chaindata  \
     --networkid 112358     \
     --rpc                  \
     --mine                 \
     --minerthreads 1       \
     --bootnodes enode://f613b39e61d78f3d8af6a9b4d3b4123330358af4f7ef471d5f45a77572c498cd55469420045453227fe818e118916eb553a39050c1369f201749e0e2fef8eb47@[::1]:30301
#    --nat "extip:$IP"      \
#    --etherbase=0x0000000000000000000000000000000000000000
#    --gasprice 1
