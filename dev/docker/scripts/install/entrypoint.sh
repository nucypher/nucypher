#!/bin/bash

# runs inside docker container with access to local volume.
# this is needed for local development
# so that the local repository is accessed
# by shared volume and is executable by 'nucypher' cli

if [ ! -e /code/nucypher.egg-info ]; then
    echo "First time install..."
    pip3 install -e .
fi