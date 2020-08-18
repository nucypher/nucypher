#!/usr/bin/env bash

# runs in circleCI's build environment
# runs finnegan's wake demo in a docker container

set -e
echo "Starting Up Finnegans Wake Demo Test..."

# Move to demo directory
cd "${0%/*}"
echo "working in directory: $PWD"

# run some ursulas
docker-compose up -d

# Wait to ensure Ursulas are up.
echo "War... watisit good for?"
sleep 3


# Run demo
echo "Starting Demo"
echo "working in directory: $PWD"
docker-compose run nucypher-circle-dev bash /code/scripts/circle/download_and_run_finnegans_wake.sh

# spit out logs
./logOutput.sh

# tear it down
docker-compose stop
