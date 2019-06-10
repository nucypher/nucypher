### Developing with Docker

The intention of the Docker configurations in this directory is to enable anyone to develop and test NuCypher on all major operating systems with minimal prerequisites and installation hassle.

#### quickstart

* install [Docker](https://docs.docker.com/install/)
* install [Docker Compose](https://docs.docker.com/compose/install/)
* cd to dev/docker (where this README is located)
* `docker-compose up --build` **this must be done once to complete install**


Then you can do things like:
* run the tests:
`docker-compose run nucypher-dev pytest`
* start up an ursula:
`docker-compose run nucypher-dev nucypher ursula run --dev --federated-only`
* open a shell:
`docker-compose run nucypher-dev bash`

* try some of the scripts in `dev/docker/scripts/`

**tested on (Ubuntu 16, MacOS 10.14, Windows 10)*

From there you can develop, modify code, test as normal.

### other cases

* run a network of 8 independent Ursulas
`docker-compose -f 8-federated-ursulas.yml up`
*  get the local ports these ursulas will be exposed on
`docker ps`
* to stop them...
 `docker-compose -f 8-federated-ursulas.yml stop`

## Pycharm (pro version only)
* You can configure pycharm to use the python interpreter inside docker.
* docs for this are [here](https://www.jetbrains.com/help/pycharm/using-docker-compose-as-a-remote-interpreter.html#docker-compose-remote)
