#!/bin/bash
args="$@"
docker run -it dev:nucpyher pytest $args