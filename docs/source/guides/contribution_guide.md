# Contributing

![NuCypher Unicorn](https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png)


## Running the Tests

``` note:: A development installation including the solidity comppiler is required to run the tests
```

There are several test implementations in `nucypher`; However, the vast majority
of test are written for execution with `pytest`.

To run the tests:

```bash
(nucypher)$ pytest -s`
```

Optionally, to run the full, slow, verbose test suite run:

```bash
(nucypher)$ pytest --runslow -s
```


## Building Documentation

``` note:: 'spinx', 'recommonmark', and 'sphinx_rtd_theme' are non-stantdard dependencies that need to be installed as part the development installation or independently in order to build documentation.
```

Documentation for `nucypher` is hosted on Read The Docs, and it automatically built without intervention by following the release procedure.
However, you may want to build the documentation html locally for development.

To build the project dependencies locally:

```bash
(nucypher)$ cd nucypher/docs/
(nucypher)$ make html
```


## Building Docker

Docker builds are automated as part of the publication workflow on circleCI and pushed to docker cloud;
However you may want to build a local version of docker for development.

We provide both a `docker-compose.yml` and a `Dockerfile` which can be used as follows:

*Docker Compose:*

```bash
(nucypher)$ docker-compose -f deploy/docker/docker-compose.yml build .
```

## Issuing a New Release with `bumpversion`

``` note:: 'bumpversion' is a non-stantdard dependency that may need to be installed as part the development installation or independently in order to issue a release.
```

1. Ensure your local tree has no uncommitted changes
2. Run `$ bumpversion devnum`
3. Ensure you have the intended history and tag: `git log`
4. Push the resulting tagged commit to the originating remote, and directly upstream `$ git push origin <TAG> && git push upstream <TAG>`
5. Monitor the triggered deployment build on circleCI for manual approval
