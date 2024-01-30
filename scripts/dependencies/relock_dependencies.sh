#!/usr/bin/env bash

# Parse optional flag -k, to be used when we want to base the process on an existing Pipfile.lock
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

# these steps might fail, but that's okay.
if ! "$KEEP_LOCK"; then
    echo "Removing existing Pipfile.lock file"
    rm -f Pipfile.lock
fi

echo "Removing existing requirement files"
pipenv --rm
rm -f $PREFIX.txt
rm -f dev-$PREFIX.txt

echo "Removing pip cache"
pip cache purge

# start enforcing failures
set -e

echo "Building Development Requirements"
pipenv --python 3.12 lock --clear --pre --dev-only
pipenv requirements --dev-only > dev-$PREFIX.txt

echo "Building Standard Requirements"
pipenv --python 3.12 lock --clear --pre
pipenv requirements > $PREFIX.txt

echo "OK!"
