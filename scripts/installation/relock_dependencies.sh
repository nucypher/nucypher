#!/usr/bin/env bash

set -e

# can change output file names with rebuild_pipenv.sh <prefix>
PREFIX=${1:-requirements}

read -p "Update your pip and setuptools? (type y or Y) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    pip install --upgrade pip
    pip install --upgrade setuptools
fi

echo "Removing existing lock files..."
pipenv --rm
rm -f Pipfile.lock
rm -f $PREFIX.txt
rm -f dev-$PREFIX.txt

read -p "Remove system pip and pipenv cache? (type y or Y) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo "Removing pip and pipenv system cache..."
    rm -r ~/.cache/pip ~/.cache/pipenv
fi

echo "Rebuilding dependency locks..."

echo "Bulding dev-$PREFIX.txt..."
pipenv lock --clear --pre --requirements --dev > dev-$PREFIX.txt

echo "Building $PREFIX.txt..."
pipenv lock --clear --pre --requirements > $PREFIX.txt

echo "Installing nucypher into new virtual enviorment..."
pipenv run pip install -e . -r dev-$PREFIX.txt

echo "Checking nucypher CLI entry point..."
pipenv run nucypher --version

echo "Committing Result..."
git add Pipfile Pipfile.lock $PREFIX.txt dev-$PREFIX.txt
git commit -m "Relock dependencies"

echo "OK!"
