#!/usr/bin/env bash

cd "${0%/*}"
echo "working in directory: $PWD"

set -e
echo "Starting Up Heartbeat Demo Test..."

# run some ursulas
docker-compose up -d

# Wait to ensure Ursulas are up.
echo "War... watisit good for?"
sleep 3

echo "running heartbeat demo"

# run alicia and bob all in one running of docker since we lack persistent disks in ci
docker-compose run nucypher-ci-dev bash /code/scripts/ci/run_heartbeat_alicia_and_bob.sh

# spit out logs
./logOutput.sh

# tear it down
docker-compose stop
