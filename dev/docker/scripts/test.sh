#!/bin/bash
args="$@"
docker run -it dev:nucypher pytest $args
