#!/usr/bin/env bash

cd "${0%/*}"
echo "working in directory: $PWD"

set -e
echo "Starting Up Heartbeat Demo Test..."

# run some ursulas
docker-compose up -d

echo "running heartbeat demo"

# run alicia and bob all in one running of docker since we lack persistent disks in circle
docker-compose run nucypher-circle-dev bash /code/scripts/circle/run_heartbeat_alicia_and_bob.sh

# spit out logs
./logOutput.sh

# tear it down
docker-compose stop
