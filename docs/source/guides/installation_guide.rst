Installation Guide
==================

Contents
--------


* `System Requirements and Dependencies <#system-requirements-and-dependencies>`_
* `Standard Installation <#standard-installation>`_
* `Docker Installation <#docker-installation>`_
* `Development Installation <#development-installation>`_
* `Running Ursula with Systemd <#systemd-service-installation>`_

System Requirements and Dependencies
------------------------------------

``nucypher`` has been tested on GNU/Linux **(recommended)**, Mac OS, and Windows.

* Before installing ``nucypher``, you may need to install necessary developer tools and headers, if you don't
  have them already. For Ubuntu, Debian, Linux Mint or similar distros:

    .. code::

       - libffi-dev
       - python3-dev
       - python3-pip
       - python3-virtualenv
       - build-essential
       - libssl-dev

    One-liner to install the above packages on linux:

    .. code:: bash

        $ sudo apt-get install python3-dev build-essential libffi-dev python3-pip

* As of November 2019, ``nucypher`` works with Python 3.6, 3.7, and 3.8. If you don’t already have it, install `Python <https://www.python.org/downloads/>`_.
* At least 1 GB of RAM for secure password-based key derivation with `scrypt <http://www.tarsnap.com/scrypt.html>`_.

.. important::

    If also running a local Ethereum node on the same machine, `additional requirements <https://docs.ethhub.io/using-ethereum/running-an-ethereum-node/>`_ are needed.


Standard Installation
---------------------

``nucypher`` can be installed by ``pip`` or ``pipenv``\ , or run with ``docker``.\
Ensure you have one of those installation tools installed for you system:


* `Pip Documentation <https://pip.pypa.io/en/stable/installing/>`_
* `Pipenv Documentation <https://pipenv.readthedocs.io/en/latest/>`_
* `Docker <https://docs.docker.com/install/>`_

Pip Installation
^^^^^^^^^^^^^^^^

In order to isolate global system dependencies from nucypher-specific dependencies, we *highly* recommend
using ``python-virtualenv`` to install ``nucypher`` inside a dedicated virtual environment.

For full documentation on virtualenv see: https://virtualenv.pypa.io/en/latest/

Here is the recommended procedure for setting up ``nucypher`` in this fashion:

#. Create a Virtual Environment

   .. code-block:: bash

       $ virtualenv /your/path/nucypher-venv
       ...

   Activate the newly created virtual environment:

   .. code-block:: bash

       $ source /your/path/nucypher-venv/bin/activate
       ...
       $(nucypher-venv)

   .. note::

       Successful virtualenv activation is indicated by ``(nucypher-venv)$`` prepended to your console's prompt


#. Install Application Code with Pip

   .. code-block:: bash

       $(nucypher-venv) pip3 install -U nucypher

#. Verify Installation

   Before continuing, verify that your ``nucypher`` installation and entry points are functional;
   Activate your virtual environment (if you haven't already) and run the ``nucypher --help`` command in the console:

   .. code-block:: bash

       nucypher --help

   You will see a list of possible usage options (\ ``--version``\ , ``-v``\ , ``--dev``\ , etc.) and commands (\ ``status``\ , ``ursula``\ , etc.).
   For example, you can use ``nucypher ursula destroy`` to delete all files associated with the node.

   .. code-block:: python

       import nucypher

Pipenv Installation
^^^^^^^^^^^^^^^^^^^

#. Install Application code with Pipenv

   Ensure you have ``pipenv`` installed (See full documentation for pipenv here: `Pipenv Documentation <https://pipenv.readthedocs.io/en/latest/>`_\ ).
   Then to install ``nucypher`` with ``pipenv``\ , run:

   .. code-block:: bash

       $ pipenv install nucypher

#. Verify Installation

   In the console:

   .. code-block:: bash

        $ nucypher --help

   In Python:

   .. code-block:: python

        import nucypher


Docker Installation
-------------------

#. Install `Docker <https://docs.docker.com/install/>`_
#. (Optional) Follow these post install instructions: `https://docs.docker.com/install/linux/linux-postinstall/ <https://docs.docker.com/install/linux/linux-postinstall/>`_
#. Get the latest nucypher image:

   .. code-block:: bash

       docker pull nucypher/nucypher:latest

   Any nucypher CLI command can be executed in docker using the following syntax:

   .. code-block:: bash

       docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 nucypher/nucypher:latest nucypher`<ACTION>``<OPTIONS>`

Examples
^^^^^^^^

Display network stats:

.. code-block::

    docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 nucypher/nucypher:latest nucypher status network --provider `<PROVIDER URI>` --network `<NETWORK NAME>`

Running a pre-configured Worker as a daemon (See :doc:`Configuration Guide </guides/network_node/ursula_configuration_guide>`):

.. code-block::

    docker run -d -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run


Development Installation
------------------------

Additional dependencies and setup steps are required to perform a "developer installation".
You do not need to perform these steps unless you intend to contribute a code or documentation change to 
the nucypher codebase.

Before continuing, ensure you have ``git`` installed (\ `Git Documentation <https://git-scm.com/doc>`_\ ).

Acquire NuCypher Codebase
^^^^^^^^^^^^^^^^^^^^^^^^^

Fork the nucypher repository on GitHub, as explained in the :doc:`Contribution Guide </guides/contribution_guide>`,
then clone your fork's repository to your local machine:

.. code-block::

    $ git clone https://github.com/<YOUR_GITHUB_USERNAME>/nucypher.git


After acquiring a local copy of the application code, you will need to
install the project dependencies, we recommend using either ``pip`` or ``pipenv``

Pipenv Development Installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The most common development installation method is using pipenv:

.. code-block:: bash

    $ pipenv install --dev --three --skip-lock --pre


Activate the pipenv shell

.. code-block:: bash

    $ pipenv shell


If this is successful, your terminal command prompt will be prepended with ``(nucypher)``

Install the Solidity compiler (solc):

.. code-block:: bash

    $(nucypher) pipenv run install-solc


Pip Development Installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Alternately, you can install the development dependencies with pip:

.. code-block:: bash

    $ pip3 install -e .[development]
    $ ./scripts/installation/install_solc.sh


Development Docker Installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The intention of the Docker configurations in this directory is to enable anyone to develop and test NuCypher on all major operating systems with minimal prerequisites and installation hassle (tested on Ubuntu 16, MacOS 10.14, Windows 10).

Standard Docker Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Install `Docker <https://docs.docker.com/install/>`_
#. Install `Docker Compose <https://docs.docker.com/compose/install/>`_
#. ``cd`` to ``dev/docker``
#. Run ``docker-compose up --build`` **this must be done once to complete install**

Running NuCypher
~~~~~~~~~~~~~~~~

Then you can do things like:

* Run the tests: ``docker-compose run nucypher-dev pytest``
* Start up an Ursula: ``docker-compose run nucypher-dev nucypher ursula run --dev --federated-only``
* Open a shell: ``docker-compose run nucypher-dev bash``
* Try some of the scripts in ``dev/docker/scripts/``

From there you can develop, modify code, test as normal.

Other cases:

* Run a network of 8 independent Ursulas: ``docker-compose -f 8-federated-ursulas.yml up``
* Get the local ports these ursulas will be exposed on: ``docker ps``
* To stop them... ``docker-compose -f 8-federated-ursulas.yml stop``

Systemd Service Installation
----------------------------

#. Use this template to create a file named ``ursula.service`` and place it in ``/etc/systemd/system/``.

   .. code-block::

       [Unit]
       Description="Run 'Ursula', a NuCypher Staking Node."

       [Service]
       User=<YOUR USER>
       Type=simple
       Environment="NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ADDRESS PASSWORD>"
       Environment="NUCYPHER_KEYRING_PASSWORD=<YOUR PASSWORD>"
       ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run

       [Install]
       WantedBy=multi-user.target


#. Replace the following values with your own:

   * ``<YOUR USER>`` - The host system's username to run the process with
   * ``<YOUR WORKER ADDRESS PASSWORD>`` - Worker's ETH account password
   * ``<YOUR PASSWORD>`` - Ursula's keyring password
   * ``<VIRTUALENV PATH>`` - The absolute path to the python virtual environment containing the ``nucypher`` executable


#. Enable Ursula System Service

   .. code-block::

       $ sudo systemctl enable ursula


#. Run Ursula System Service

   To start Ursula services using systemd

   .. code-block::

       $ sudo systemctl start ursula


#. Check Ursula service status

   .. code-block::

       $ sudo systemctl status ursula

#. To restart your node service

   .. code-block:: bash

       $ sudo systemctl restart ursula
