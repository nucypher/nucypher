Installation Reference
======================

``nucypher`` can be run either from a docker container or via local installation. Running ``nucypher``
via a docker container simplifies the installation process and negates the need for a local installation.


.. _docker-installation:

Docker Installation and Update
------------------------------

#. Install `Docker <https://docs.docker.com/install/>`_
#. *Optional* Depending on the setup you want, post install instructions, additional
   docker configuration is available `here <https://docs.docker.com/engine/install/linux-postinstall/>`_.
#. Get the latest nucypher image:

.. code:: bash

    docker pull nucypher/nucypher:latest

.. _local-installation:

Local Installation
------------------

``nucypher`` supports Python 3.8, 3.9, 3.10, and 3.11. If you don’t already have it, install `Python <https://www.python.org/downloads/>`_.

In order to isolate global system dependencies from nucypher-specific dependencies, we *highly* recommend
using ``python-virtualenv`` to install ``nucypher`` inside a dedicated virtual environment.

For full documentation on virtualenv see: https://virtualenv.pypa.io/en/latest/:

#. Create a Virtual Environment

   Create a virtual environment in a folder somewhere on your machine.This virtual
   environment is a self-contained directory tree that will contain a python
   installation for a particular version of Python, and various installed packages needed to run the node.

   .. code-block:: bash

       $ python -m venv /your/path/nucypher-venv
       ...


#. Activate the newly created virtual environment:

   .. code-block:: bash

       $ source /your/path/nucypher-venv/bin/activate
       ...
       (nucypher-venv)$


   A successfully activated virtual environment is indicated by ``(nucypher-venv)$`` prepended to your console's prompt

   .. note::

       From now on, if you need to execute any ``nucypher`` commands you should do so within the activated virtual environment.


#. Install/Update the ``nucypher`` package

   .. code-block:: bash

       (nucypher-venv)$ pip3 install -U nucypher


#. Verify Installation

    Before continuing, verify that your ``nucypher`` installation and entry points are functional.

    Activate your virtual environment, if not activated already:

    .. code-block:: bash

       $ source /your/path/nucypher-venv/bin/activate

    Next, verify ``nucypher`` is importable.  No response is successful, silence is golden:

    .. code-block:: bash

       (nucypher-venv)$ python -c "import nucypher"

    Then, run the ``nucypher --help`` command:

    .. code-block:: bash

       (nucypher-venv)$ nucypher --help
       ...

    If successful you will see a list of possible usage options (\ ``--version``\ , ``--config-path``\ , ``--logging-path``\ , etc.) and
    commands (\ ``status``\ , ``ursula``\ , etc.).
