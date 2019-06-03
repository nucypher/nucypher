#!/usr/bin/env bash

echo "Downloading Finnegan's Wake Text..."
wget "https://github.com/nucypher/nucypher/files/1765576/finnegans-wake.txt" -O ./finnegans-wake.txt
echo "Successfully downloaded. To run the demo execute 'python finnegans-wake-demo.py'"
