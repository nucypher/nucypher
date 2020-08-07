Contributing
============

.. image:: https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png
    :target: https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png


Acquiring the Codebase
----------------------

.. _`NuCypher GitHub`: https://github.com/nucypher/nucypher

In order to contribute new code or documentation changes, you will need a local copy
of the source code which is located on the `NuCypher GitHub`_.

.. note::

   NuCypher uses ``git`` for version control. Be sure you have it installed.

Here is the recommended procedure for acquiring the code in preparation for
contributing proposed changes:


1. Use GitHub to fork the ``nucypher/nucypher`` repository

2. Clone your fork's repository to your local machine

.. code-block:: bash

   $ git clone https://github.com/<YOUR-GITHUB-USERNAME>/nucypher.git

3. Change directory to ``nucypher``

.. code-block:: bash

   $ cd nucypher

4. Add ``nucypher/nucypher`` as an upstream remote

.. code-block:: bash

   $ git remote add upstream https://github.com/nucypher/nucypher.git

5. Update your remote tracking branches

.. code-block:: bash

   $ git remote update

.. _`Developer Installation Guide`: https://docs.nucypher.com/en/latest/guides/installation_guide.html

6. Install the project dependencies: see the `Developer Installation Guide`_


Running the Tests
-----------------

.. note::

  A development installation including the solidity compiler is required to run the tests


.. _Pytest Documentation: https://docs.pytest.org/en/latest/

There are several test implementations in ``nucypher``, however, the vast majority
of test are written for execution with ``pytest``.
For more details see the `Pytest Documentation`_.


To run the tests:

.. code:: bash

  (nucypher)$ pytest -s


Optionally, to run the full, slow, verbose test suite run:

.. code:: bash

  (nucypher)$ pytest --runslow -s


Making a Commit
---------------

NuCypher takes pride in its commit history.

When making a commit that you intend to contribute, keep your commit descriptive and succinct.
Commit messages are best written in full sentences that make an attempt to accurately
describe what effect the changeset represents in the simplest form.  (It takes practice!)

Imagine you are the one reviewing the code, commit-by-commit as a means of understanding
the thinking behind the PRs history. Does your commit history tell an honest and accurate story?

We understand that different code authors have different development preferences, and others
are first-time contributors to open source, so feel free to join our `Discord <https://discord.gg/7rmXa3S>`_ and let us know
how we can best support the submission of your proposed changes.


Opening a Pull Request
----------------------

When considering including commits as part of a pull request into ``nucypher/nucypher``,
we *highly* recommend opening the pull request early, before it is finished with
the mark "[WIP]" prepended to the title.  We understand PRs marked "WIP" to be subject to change,
history rewrites, and CI failures. Generally we will not review a WIP PR until the "[WIP]" marker
has been removed from the PR title, however, this does give other contributors an opportunity
to provide early feedback and assists in facilitating an iterative contribution process.


Pull Request Conflicts
----------------------

As an effort to preserve authorship and a cohesive commit history, we prefer if proposed contributions
are rebased over ``main`` (or appropriate branch) when a merge conflict arises
instead of making a merge commit back into the contributors fork.

Generally speaking the preferred process of doing so is with an `interactive rebase`:

.. important::

   Be certain you do not have uncommitted changes before continuing.

1. Update your remote tracking branches

.. code-block:: bash

   $ git remote update
   ...  (some upstream changes are reported)

2. Initiate an interactive rebase over ``nucypher/nucypher@main``

.. note::

   This example specifies the remote name ``upstream`` for the NuCypher organizational repository as
   used in the `Acquiring the Codebase`_ section.

.. code-block:: bash

   $ git rebase -i upstream/main
   ...  (edit & save rebase TODO list)

3. Resolve Conflicts

.. code-block:: bash

   $ git status
   ... (resolve local conflict)
   $ git add path/to/resolved/conflict/file.py
   $ git rebase --continue
   ... ( repeat as needed )


4. Push Rebased History

After resolving all conflicts, you will need to force push to your fork's repository, since the commits
are rewritten.

.. warning::

   Force pushing will override any changes on the remote you push to, proceed with caution.

.. code-block:: bash

   $ git push origin my-branch -f


Building Documentation
----------------------

.. note::

  ``sphinx`` and ``sphinx_rtd_theme`` are non-standard dependencies that can be installed
  by running ``pip install -e .[docs]`` from the project directory.


.. _Read The Docs: https://nucypher.readthedocs.io/en/latest/

Documentation for ``nucypher`` is hosted on `Read The Docs`_, and is automatically built without intervention by following the release procedure.
However, you may want to build the documentation html locally for development.

To build the project dependencies locally:

.. code:: bash

    (nucypher)$ make docs


If the build is successful, the resulting html output can be found in ``nucypher/docs/build/html``;
Opening ``nucypher/docs/build/html/index.html`` in a web browser is a reasonable next step.


Building Docker
---------------

Docker builds are automated as part of the publication workflow on circleCI and pushed to docker cloud.
However you may want to build a local version of docker for development.

We provide both a ``docker-compose.yml`` and a ``Dockerfile`` which can be used as follows:

*Docker Compose:*

.. code:: bash

  (nucypher)$ docker-compose -f deploy/docker/docker-compose.yml build .


Issuing a New Release
---------------------

.. note::

  This process uses ``towncrier`` and ``bumpversion``, which can be installed by running ``pip install -e .[deploy]`` or ``pip install towncrier bumpversion``.
  Also note that it requires you have git commit signing properly configured.

.. important::

   Ensure your local tree is based on ``main`` and has no uncommitted changes.

1. Decide what part of the version to bump.
The version string follows the format ``{major}.{minor}.{patch}-{stage}.{devnum}``,
so the options are ``major``, ``minor``, ``patch``, ``stage``, or ``devnum``.
We usually issue new releases increasing the ``devnum`` version.

2. Use the ``make release`` script, specifying the version increment with the ``bump`` parameter.
For example, for a new ``devnum`` release, we would do:

.. code:: bash

  (nucypher)$ make release bump=devnum

3. The previous step triggers the publication webhooks on CircleCI.
Monitor the triggered deployment build for manual approval.
