#!/usr/bin/env bash

# runs in docker on circle ci

set -e
/code/examples/finnegans_wake_demo/download_finnegans_wake.sh
python /code/examples/finnegans_wake_demo/finnegans-wake-demo.py 172.29.1.3:11500
