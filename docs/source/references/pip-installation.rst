Installation Reference
======================

.. _base-requirements:

Linux/Mac Software Dependencies
---------------------------------

* ``nucypher`` supports Python 3.7 and 3.8. If you don’t already have it, install `Python <https://www.python.org/downloads/>`_.
* Before installing ``nucypher``, you may need to install necessary developer tools and headers:

    .. code::

       - libffi-dev
       - python3-dev
       - python3-pip
       - python3-virtualenv
       - build-essential
       - libssl-dev

Pip Installation and Update
----------------------------

In order to isolate global system dependencies from nucypher-specific dependencies, we *highly* recommend
using ``python-virtualenv`` to install ``nucypher`` inside a dedicated virtual environment.

For full documentation on virtualenv see: https://virtualenv.pypa.io/en/latest/:

#. Create a Virtual Environment

   .. code-block:: bash

       $ python -m venv /your/path/nucypher-venv
       ...

   Activate the newly created virtual environment:

   .. code-block:: bash

       $ source /your/path/nucypher-venv/bin/activate
       ...
       $(nucypher-venv)

   .. note::

       Successful virtualenv activation is indicated by ``(nucypher-venv)$`` prepended to your console's prompt


#. Install/Update Application Code with Pip

   .. code-block:: bash

       (nucypher-venv) pip3 install -U nucypher

#. Verify Installation

    Before continuing, verify that your ``nucypher`` installation and entry points are functional.

    Activate your virtual environment:

    .. code-block:: bash

       user@ubuntu$ source /your/path/nucypher-venv/bin/activate

    Next, verify nucypher is importable.  No response is successful. silence is golden:

    .. code-block:: python

       python -c "import nucypher"

    Then, run the ``nucypher --help`` command:

    .. code-block:: bash

       (nucypher) user@ubuntu$ nucypher --help
       ...

    If successful you will see a list of possible usage options (\ ``--version``\ , ``-v``\ , ``--dev``\ , etc.) and
    commands (\ ``status``\ , ``ursula``\ , etc.). For example, you can use ``nucypher ursula init`` initialize a new worker node.
