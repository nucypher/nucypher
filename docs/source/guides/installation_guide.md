# Installation Guide


## Contents

* [System Requirements and Dependencies](#System-Requirements-and-Dependencies)
* [Standard Installation](#Standard-Installation)
* [Docker Installation](#Docker-Installation)
* [Development Installation](#Development-Installation)
* [Development Docker Installation](#Development-Docker-Installation)
* [Running Ursula with Systemd](#Systemd-Service-Installation)

## System Requirements and Dependencies

* At least 1 GB of RAM is required for secure password-based key derivation with [scrypt](http://www.tarsnap.com/scrypt.html).
* We have tested `nucypher` with Windows, Mac OS, and GNU/Linux (GNU/Linux is recommended).
* If you don’t already have it, install [Python](https://www.python.org/downloads/).
As of August 2019, we are working with Python 3.6, 3.7, and 3.8.
* We also require the following system packages (Linux):

    - `libffi-dev`
    - `python3-dev`
    - `python3-virtualenv`

## Standard Installation

We recommend installing `nucypher` with either `pip` or `pipenv`

* [Pip Documentation](https://pip.pypa.io/en/stable/installing/)
* [Pipenv Documentation](https://pipenv.readthedocs.io/en/latest/)

### Standard Pip Installation

In order to isolate global system dependencies from nucypher-specific dependencies, we *highly* recommend
using `python-virtualenv` to install `nucypher` inside a dedicated virtual environment.

For full documentation on virtualenv see: <https://virtualenv.pypa.io/en/latest/>

Here is the recommended procedure for setting up `nucypher` in this fashion:

1. Create a Virtual Environment

    ```bash
    $ virtualenv /your/path/nucypher-venv
    ...
    ```

    Activate the newly created virtual environment:

    ```bash
    $ source /your/path/nucypher-venv/bin/activate
    ...
    $(nucypher-venv)
    ```

    ``` note:: Successful virtualenv activation is indicated by '(nucypher-venv)$' prepended to your console's prompt
    ```


2. Install Application Code with Pip

    ```bash
    $(nucypher-venv) pip3 install -U nucypher
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
    Then to install `nucypher` with `pipenv`, run:

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

## Standard Docker Install
##### --- for running Nucypher Nodes and using Nucypher Characters
* install [Docker](https://docs.docker.com/install/)
* (optional) follow these post install instructions: https://docs.docker.com/install/linux/linux-postinstall/
* get the latest nucypher image:
  * `(maybe sudo) docker pull nucypher/nucypher:latest`
* that's it.  Now you can `docker run -v /home/ubuntu:/root/.local/share/ nucypher/nucypher:latest nucypher alice init`

    * *Note the volume mounts. `-v <path to a directory on your computer>:/root/.local/share/`
This is important because it allows your Nucypher node to store persistent data as well as commonly access ipc with a locally running geth node.*


Here is an example of how to run an Ursula worker node on Ubuntu. It assumes you have a geth node running locally with `--datadir=~/geth`


```
export NUCYPHER_KEYRING_PASSWORD=<your keyring password>
export MY_IP=$(wget -q -O - ifconfig.me);
export NUCYPHER_WORKER_ADDRESS=<eth account checksum of your worker>
export NUCYPHER_STAKER_ADDRESS=<eth account checksum of your staker>
export NUCYPHER_WORKER_ETH_PASSWORD=<your eth account password>

# init your worker
docker run -v /home/ubuntu:/root/.local/share/ -e NUCYPHER_KEYRING_PASSWORD -it nucypher/nucypher:latest nucypher ursula init --provider /root/.local/share/geth/.ethereum/goerli/geth.ipc --poa --worker-address $NUCYPHER_WORKER_ADDRESS --staker-address $NUCYPHER_STAKER_ADDRESS --rest-host $MY_IP --sync

# and then run the worker in the background
docker run -v /home/ubuntu:/root/.local/share/ -dit --restart unless-stopped -p 9151:9151  -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD  nucypher/nucypher:latest nucypher ursula run --teacher discover.nucypher.network:9151 --sync --poa
```

## Development Docker Installation
##### --- for using docker for easier Nucypher development
The intention of the Docker configurations in this directory is to enable anyone to develop and test NuCypher on all major operating systems with minimal prerequisites and installation hassle.

### Start with standard Docker Installation
* install [Docker](https://docs.docker.com/install/)
* install [Docker Compose](https://docs.docker.com/compose/install/)
* cd to dev/docker
* `docker-compose up --build` **this must be done once to complete install**

### Running NuCypher
Then you can do things like:
* run the tests:
`docker-compose run nucypher-dev pytest`
* start up an ursula:
`docker-compose run nucypher-dev nucypher ursula run --dev --federated-only`
* open a shell:
`docker-compose run nucypher-dev bash`

* try some of the scripts in `dev/docker/scripts/`

**tested on (Ubuntu 16, MacOS 10.14, Windows 10)*

From there you can develop, modify code, test as normal.

### Other cases

* run a network of 8 independent Ursulas
`docker-compose -f 8-federated-ursulas.yml up`
*  get the local ports these ursulas will be exposed on
`docker ps`
* to stop them...
 `docker-compose -f 8-federated-ursulas.yml stop`


## Development Installation

Additional dependencies and setup steps are required to perform a "developer installation".
Ensure you have `git` installed ([Git Documentation](https://git-scm.com/doc)).


### Acquire NuCypher Codebase

Fork the nucypher repository on GitHub, as explained in the [Contribution Guide](/guides/contribution_guide),
then clone your fork's repository to your local machine:

```
$ git clone https://github.com/<YOUR_GITHUB_USERNAME>/nucypher.git
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

Install the Solidity compiler (solc):

```bash
$(nucypher) pipenv run install-solc
```

### Pip Development Installation

Alternately, you can install the development dependencies with pip:

```bash
$ pip3 install -e .[development]
$ ./scripts/installation/install_solc.sh
```

## Systemd Service Installation

1. Use this template to create a file named `ursula.service` and place it in `/etc/systemd/system/`.

    ```
    [Unit]
    Description="Run 'Ursula', a NuCypher Staking Node."

    [Service]
    User=<YOUR USER>
    Type=simple
    Environment="NUCYPHER_KEYRING_PASSWORD=<YOUR PASSWORD>"
    ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run --teacher <SEEDNODE_URI>

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
