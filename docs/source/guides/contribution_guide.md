# Contributing

![NuCypher Unicorn](https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png)


## Running the Tests

``` note:: A development installation including the solidity comppiler is required to run the tests
```

There are several test implementations in `nucypher`; However, the vast majority
of test are written for execution with `pytest`.
For more details see the [Pytest Documentation](https://docs.pytest.org/en/latest/)

To run the tests:

```bash
(nucypher)$ pytest -s`
```

Optionally, to run the full, slow, verbose test suite run:

```bash
(nucypher)$ pytest --runslow -s
```

## Building Documentation

``` note:: 'spinx', 'recommonmark', and 'sphinx_rtd_theme' are non-stantdard dependencies that be installed by running 'pip install -e .[docs]' from the project directory.
```

Documentation for `nucypher` is hosted on Read The Docs, and it automatically built without intervention by following the release procedure.
However, you may want to build the documentation html locally for development.

To build the project dependencies locally:

```bash
(nucypher)$ cd nucypher/docs/
(nucypher)$ make html
```

If the build is successful, the resulting html output can be found in `nucypher/docs/build/html`;
Opening `nucypher/docs/build/html/index.html` in a web browser is a reasonable next step.


## Building Docker

Docker builds are automated as part of the publication workflow on circleCI and pushed to docker cloud;
However you may want to build a local version of docker for development.

We provide both a `docker-compose.yml` and a `Dockerfile` which can be used as follows:

*Docker Compose:*

```bash
(nucypher)$ docker-compose -f deploy/docker/docker-compose.yml build .
```

## Issuing a New Release

``` note:: 'bumpversion' is a non-stantdard dependency that can be installed by running 'pip install -e .[deployment]' or 'pip install bumpversion'.
```

1. Ensure your local tree has no uncommitted changes
2. Run `$ bumpversion devnum`
3. Ensure you have the intended history and tag: `git log`
4. Push the resulting tagged commit to the originating remote, and directly upstream `$ git push origin <TAG> && git push upstream <TAG>`
5. Monitor the triggered deployment build on circleCI for manual approval
