#!/usr/bin/env bash

# can change output file names with relock_dependencies.sh <prefix>
PREFIX=${1:-requirements}

# these steps might fail, but that's okay.
echo "Removing existing lock files..."
pipenv --rm
rm -f Pipfile.lock
rm -f $PREFIX.txt
rm -f dev-$PREFIX.txt
rm -f docs-$PREFIX.txt

echo "Removing pip and pipenv system cache..."
rm -r ~/.cache/pip ~/.cache/pipenv

# start enforcing failures
set -e

echo "Building Documentation Requirements"
pushd ./scripts/dependencies/docs
pipenv lock --clear --pre --requirements --no-header > ../../../docs-$PREFIX.txt
rm -f Pipfile.lock
pipenv --rm
popd

echo "Building Development Requirements"
pipenv lock --clear --pre --requirements --dev-only --no-header > dev-$PREFIX.txt

echo "Building Standard Requirements"
pipenv lock --clear --pre --requirements --no-header > $PREFIX.txt

echo "OK!"
