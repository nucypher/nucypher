#!/usr/bin/env bash

set -e

yes | ./scripts/installation/rebuild_pipenv.sh circlereqs

if [ $(md5 -q requirements.txt) == $(md5 -q circlereqs.txt) ]; then
    echo "requirements.txt is valid"

else
    echo "requirements.txt contains inconsistencies"
    diff requirements.txt circlereqs.txt
    exit 2
fi

if [ $(md5 -q dev-requirements.txt) == $(md5 -q dev-circlereqs.txt) ]; then
    echo "requirements.txt is valid"

else
    echo "dev-requirements.txt contains inconsistencies"
    diff dev-requirements.txt dev-circlereqs.txt
    exit 2
fi