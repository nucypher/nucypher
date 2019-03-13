### Developing with Docker

The intention of the Docker configurations in this directory is to enable anyone to develop and test NuCypher on all major operating systems with minimal prerequisites and installation hassle.

#### quickstart

* install [Docker](https://docs.docker.com/install/)
* install [Docker Compose](https://docs.docker.com/compose/install/)
* cd to dev/docker (where this README is located)
* `docker-compose up` **this must be done once to complete install**


Then you can do things like:
* run the tests:
`docker run -it dev:nucypher pytest`
* start up an ursula:
`docker run -it dev:nucypher nucypher ursula run --dev --federated-only"`
* open a shell:
`docker run -it dev:nucypher bash`

* try some of the scripts in `dev/docker/scripts/`

**tested on (Ubuntu 16, MacOS 10.14, Windows 10)*

From there you can develop, modify code, test as normal.

### other cases

* run a network of three independent Ursulas
`docker-compose -f 3-ursulas.yml up`
*  get the local ports these ursulas will be exposed on
`docker ps`
* to stop them...
 `docker-compose -f 3-ursulas.yml stop`
