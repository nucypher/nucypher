#!/usr/bin/env bash

LOGDIR=/tmp/ursulas-logs
mkdir $LOGDIR
docker exec -it circleursula1 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-1.txt
docker exec -it circleursula2 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-2.txt
docker exec -it circleursula3 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-3.txt
docker exec -it circleursula4 cat /root/.cache/nucypher/log/nucypher.log > $LOGDIR/ursula-4.txt
