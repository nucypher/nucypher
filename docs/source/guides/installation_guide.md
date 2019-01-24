# Installation Guide


## System Requirements

* At least 1 GB or RAM is required for key derivation functionality (SCrypt).
* We have tested `nucypher` with windows, mac OS, and linux.


## System Dependencies

If you don’t already have them, install Python;.
As of January 2019, we are working with Python 3.6, 3.7, and 3.8.

* Official Python Website: <https://www.python.org/downloads/>


We also require the following system packages (Linux):

    - libffi-dev
    - python3-dev
    - python3-virtualenv

## Standard Installation

We recommend installing nucypher with either `pip` or `pipenv`

* [Pip Documentation](https://pip.pypa.io/en/stable/installing/)
* [Pipenv Documentation](https://pipenv.readthedocs.io/en/latest/)

### Standard Pip Installation

In order to isolate global system dependencies from nucypher-specific dependencies, we *highly* recommend
using `python-vitrualenv`, Installing `nucypher` and it's dependencies inside a dedicated virtual environment.

Full full documentation on virtualenv see: <https://virtualenv.pypa.io/en/latest/>

Here is the recommended procedure for setting up `nucypher` in this fashion:

1. Create a Virtual Environment

    ```bash
    $ virtualenv /your/path/nucypher-venv
    ...
    ```
    
    Activate the newly created virtual environment:
    
    ```bash
    $ source /your/path/nucypher-venv
    ...
    $(nucypher-venv)
    ```

    ``` note:: Successful virtualenv activation is indicated by '(nucypher-venv)$' prepending your console's prompt
    ```


2. Install Application Code with Pip
    
    ```bash
    $(nucypher-venv) pip install -U nucypher
    ```


3. Verify Installation

    In the console:

    ```bash
    nucypher --help
    ```

    In Python:

    ```python
    import nucypher
    ```

### Standard Pipenv Installation


1. Install Application code with Pipenv
    
    Ensure you have `pipenv` installed (See full documentation for pipenv here: [Pipenv Documentation](https://pipenv.readthedocs.io/en/latest/)).
    Then, to install nucypher with pipenv run:
    
    ```bash
    $ pipenv install nucypher
    ```


2. Verify Installation

    In the console:

    ```bash
    nucypher --help
    ```

    In Python:

    ```python
    import nucypher
    ```

## Development Installation

Additional dependencies and setup steps are required to perform a "developer installation".
Ensure you have `git` installed ([Git Documentation](https://git-scm.com/doc)).

### Acquire NuCypher Codebase
    
```
$ git clone https://github.com/nucypher/nucypher.git
```

After acquiring a local copy of the application code, you will need to
install the project dependencies, we recommend using either `pip` or `pipenv`

### Pipenv Development Installation

The most common development installation method is using pipenv:

```bash
$ pipenv install --dev --three --skip-lock --pre
```

Activate the pipenv shell

```bash
$ pipenv shell
```

If this is successful, your terminal command prompt will be prepended with `(nucypher)`

Install the solidity compiler:

```bash
$(nucypher) pipenv run install-solc
```
    
### Pip Development Installation
    
Alternately, you can install the development dependencies with pip:

```bash
$ pip install -e .[testing]
$ ./scripts/install_solc.sh
```

## Systemd Service Installation

1. Use this template to create a file named  ursula.service and place it in */etc/systemd/system/*.

    ```
    [Unit]
    Description="Run 'Ursula', a NuCypher Staking Node."
    
    [Service]
    User=<YOUR USER>
    Type=simple
    Environment="NUCYPHER_KEYRING_PASSWORD=<YOUR PASSWORD>"
    ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run --teacher-uri <SEEDNODE_URI>
    
    [Install]
    WantedBy=multi-user.target
    ```
    
    Replace the following values with your own:
    
    * `<YOUR_USER>` - The host system's username to run the process with
    * `<YOUR_PASSWORD>` - Ursula's keyring password
    * `<VIRTUALENV_PATH>` - The absolute path to the python virtual environment containing the `nucypher` executable
    * `<SEEDNODE_URI>` - A seednode URI of a node on the network you are connecting to

2. Enable Ursula System Service

    ```
    $ sudo systemctl enable ursula
    ```

3. Run Ursula System Service

    To start Ursula services using systemd

    ```
    $ sudo systemctl start ursula
    ```

4. Check Ursula service status

    ```
    $ sudo systemctl status ursula
    ```

5. To restart your node service

    ```
    $ sudo systemctl restart ursula
    ```
