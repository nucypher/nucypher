#!/usr/bin/env bash

set -e
echo "Starting Up Finnegans Wake Demo Test..."

COMPOSE_FILE="${0%/*}/../../dev/docker/8-federated-ursulas.yml"
DEMO_DIR="/code/examples/finnegans_wake_demo/"

# run some ursulas
docker-compose -f $COMPOSE_FILE up -d
echo "Wait for Ursula learning to occur"
sleep 5

# Download book text
echo "Download Book Text"
docker-compose -f $COMPOSE_FILE run -w $DEMO_DIR nucypher-dev bash download_finnegans_wake.sh

# Run demo
echo "Starting Demo"
docker-compose -f $COMPOSE_FILE run -w $DEMO_DIR nucypher-dev python finnegans-wake-demo.py 172.28.1.3:11500

# tear it down
docker-compose -f $COMPOSE_FILE stop
