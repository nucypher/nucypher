#!/usr/bin/env bash

# can change output file names with rebuild_pipenv.sh <prefix>
PREFIX=${1:-requirements}

read -p "Ok if we update your pip and setuptools? (type y or Y) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    pip install --upgrade pip
    pip install --upgrade setuptools
fi

rm $PREFIX.txt
rm dev-$PREFIX.txt

touch $PREFIX.txt
touch dev-$PREFIX.txt

set -e
echo "rebuilding pipenv.lock... this will take awhile."

echo "bulding dev-$PREFIX.txt"
pipenv lock --clear --pre --requirements --dev > dev-$PREFIX.txt

echo "building $PREFIX.txt"
pipenv lock --clear --pre --requirements > $PREFIX.txt

