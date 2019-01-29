Contributing
============

.. image:: https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png
    :target: https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png


Running the Tests
-----------------

.. note::

  A development installation including the solidity compiler is required to run the tests


.. _Pytest Documentation: https://docs.pytest.org/en/latest/

There are several test implementations in `nucypher`, however, the vast majority
of test are written for execution with `pytest`.
For more details see the `Pytest Documentation`_


To run the tests:

.. code:: bash

  (nucypher)$ pytest -s


Optionally, to run the full, slow, verbose test suite run:

.. code:: bash

  (nucypher)$ pytest --runslow -s

Building Documentation
----------------------

.. note::

  `sphinx`, `recommonmark`, and `sphinx_rtd_theme` are non-standard dependencies that can be installed by running `pip install -e .[docs]` from the project directory.


.. _Read The Docs: https://nucypher.readthedocs.io/en/latest/

Documentation for `nucypher` is hosted on `Read The Docs`_, and is automatically built without intervention by following the release procedure.
However, you may want to build the documentation html locally for development.

To build the project dependencies locally:

.. code:: bash

    (nucypher)$ cd nucypher/docs/
    (nucypher)$ make html


If the build is successful, the resulting html output can be found in `nucypher/docs/build/html`;
Opening `nucypher/docs/build/html/index.html` in a web browser is a reasonable next step.


Building Docker
---------------

Docker builds are automated as part of the publication workflow on circleCI and pushed to docker cloud.
However you may want to build a local version of docker for development.

We provide both a `docker-compose.yml` and a `Dockerfile` which can be used as follows:

*Docker Compose:*

.. code:: bash

  (nucypher)$ docker-compose -f deploy/docker/docker-compose.yml build .


Issuing a New Release
---------------------

.. note::
  `bumpversion` is a non-standard dependency that can be installed by running `pip install -e .[deployment]` or 'pip install bumpversion'.

1. Ensure your local tree has no uncommitted changes
2. Run `$ bumpversion devnum`
3. Ensure you have the intended history and tag: `git log`
4. Push the resulting tagged commit to the originating remote, and directly upstream `$ git push origin <TAG> && git push upstream <TAG>`
5. Monitor the triggered deployment build on circleCI for manual approval
