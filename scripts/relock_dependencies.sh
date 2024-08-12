#!/usr/bin/env bash

# Parse optional flag -k, to be used when we want to base the process on an existing poetry.lock
KEEP_LOCK=false
OPTIND=1
while getopts 'k' opt; do
    case $opt in
        k) KEEP_LOCK=true ;;
        *) echo 'Error in command line parsing' >&2
           exit 1
    esac
done
shift "$(( OPTIND - 1 ))"

# can change output file names with relock_dependencies.sh <prefix>
PREFIX=${1:-requirements}

# setup export plugin
poetry self add poetry-plugin-export
poetry config warnings.export false

# update poetry and pip
poetry self update
pip install --upgrade pip

# these steps might fail, but that's okay.
if ! "$KEEP_LOCK"; then
    echo "Removing existing poetry.lock file"
    rm -f poetry.lock
fi

echo "Removing existing requirement files"
rm -f $PREFIX.txt
rm -f dev-$PREFIX.txt

echo "Removing pip cache"
pip cache purge

# start enforcing failures
set -e

echo "Building Development Requirements"
poetry lock
poetry export -o dev-requirements.txt --without-hashes --with dev

echo "Building Standard Requirements"
poetry export -o requirements.txt --without-hashes --without dev

echo "OK!"
