#!/usr/bin/env bash

LOGDIR=/tmp/ursulas-logs
mkdir $LOGDIR
docker exec ciursula1 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-1.txt
docker exec ciursula2 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-2.txt
docker exec ciursula3 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-3.txt
docker exec ciursula4 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-4.txt
