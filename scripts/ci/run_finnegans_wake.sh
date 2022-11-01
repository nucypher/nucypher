#!/usr/bin/env bash

# runs in docker on ci

set -e
python /code/examples/finnegans_wake_demo/finnegans-wake-demo-federated.py 172.29.1.3:11500
