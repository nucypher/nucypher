#!/usr/bin/env bash

curl --user ${CIRCLE_API_TOKEN}: \
     --request POST \
     --form build_parameters[CIRCLE_JOB]=${JOB_NAME} \
     --form build_parameters[CIRCLE_REPOSITORY_URL]=${CIRCLE_GIT_URL} \
     --form config=@config.yml \
     --form notify=false \
     https://circleci.com/api/v1.1/project/github/nucypher/nucypher/
