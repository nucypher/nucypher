#!/usr/bin/env bash

set -e

# Update lock and build requirements files.
# Use option -k to keep the Pipfile.lock file, so the process is deterministic with respect to that file.
yes | ./scripts/dependencies/relock_dependencies.sh -k circle-requirements

echo "---- Validating requirements.txt ----"
REQSHASH=$(md5sum requirements.txt | cut -d ' ' -f1)
TESTHASH=$(md5sum circle-requirements.txt | cut -d ' ' -f1)

echo "- $REQSHASH"
echo "- $TESTHASH"
if [ $REQSHASH == $TESTHASH ]; then
    echo "- requirements.txt is valid ...."
else
    echo "- requirements.txt contains inconsistencies ...."
    echo "- you may want to run `pipenv sync --dev` and then ./scripts/dependencies/relock_dependencies.sh ...."
    echo "- which will rebuild your *requirements.txt files ...."
    diff requirements.txt circle-requirements.txt
    exit 2
fi

echo "---- Validating dev-requirements.txt ----"
REQSHASH=$(md5sum dev-requirements.txt | cut -d ' ' -f1)
TESTHASH=$(md5sum dev-circle-requirements.txt | cut -d ' ' -f1)

echo "- $REQSHASH"
echo "- $TESTHASH"

if [ $REQSHASH == $TESTHASH ]; then
    echo "- dev-requirements.txt is valid ...."
else
    echo "- dev-requirements.txt contains inconsistencies ...."
    echo "- you may want to run `pipenv sync --dev` and then ./scripts/dependencies/relock_dependencies.sh ...."
    echo "- which will rebuild your *requirements.txt files ...."
    diff dev-requirements.txt dev-circle-requirements.txt
    exit 2
fi
