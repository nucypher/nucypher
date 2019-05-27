#!/usr/bin/env bash

read -p "Ok if we update your pip and setuptools? (type y or Y) " -n 1 -r
echo 
if [[ $REPLY =~ ^[Yy]$ ]]
then
    pip install --upgrade pip
    pip install --upgrade setuptools
fi

rm requirements.txt
rm dev-requirements.txt

touch requirements.txt
touch dev-requirements.txt

set -e 
echo "rebuilding pipenv.lock... this will take awhile."
pipenv lock --clear

pipenv lock -r > requirements.txt
pipenv lock -r --dev > dev-requirements.txt


