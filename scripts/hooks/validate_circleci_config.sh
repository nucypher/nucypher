#!/usr/bin/env bash

# The following line is needed by the CircleCI Local Build Tool (due to Docker interactivity)
exec < /dev/tty

echo "Validating CircleCI YML Config..."
# If validation fails, tell Git to stop and provide error message. Otherwise, continue.
if ! eMSG=$(circleci config validate -c .circleci/config.yml); then
	echo "CircleCI Configuration Failed Validation."
	echo $eMSG
	exit 1
fi
echo "CircleCI config is valid."
