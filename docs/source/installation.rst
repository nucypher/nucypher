Installation Reference
======================

Contents
--------

* `System Requirements and Dependencies`_
* `Standard Installation`_
* `Docker Installation`_


.. _base-requirements:

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


Docker Installation
-------------------

.. note::

    Due to dependency requirements, the ``nucypher`` docker image can only be run on x86 architecture.


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

Running a pre-configured Worker as a daemon (See :doc:`Configuration Guide </staking/running_a_worker>`):

.. code-block::

    docker run -d -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run
