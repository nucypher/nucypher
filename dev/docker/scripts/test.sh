#!/bin/bash
args="$@"
docker-compose run nucypher-dev pytest $args
