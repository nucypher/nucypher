#!/usr/bin/env bash

set -e
echo "Starting Up Heartbeat Demo Test..."

COMPOSE_FILE="${0%/*}/../../dev/docker/8-federated-ursulas.yml"
DEMO_DIR="/code/examples/heartbeat_demo/"

# run some ursulas
docker-compose -f $COMPOSE_FILE up -d
echo "Wait for Ursula learning to occur"
sleep 5

# Run Alicia
echo "Starting Alicia..."
docker-compose -f $COMPOSE_FILE run -w $DEMO_DIR nucypher-dev python3 alicia.py 172.28.1.3:11500

# Run Dr. Bob
echo "Starting Bob..."
docker-compose -f $COMPOSE_FILE run -w $DEMO_DIR nucypher-dev python3 doctor.py 172.28.1.3:11500

# tear it down
docker-compose -f $COMPOSE_FILE stop
