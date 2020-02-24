# Installation Guide


## Contents

* [System Requirements and Dependencies](#system-requirements-and-dependencies)
* [Standard Installation](#standard-installation)
* [Docker Installation](#docker-installation)
* [Development Installation](#development-installation)
* [Running Ursula with Systemd](#systemd-service-installation)

## System Requirements and Dependencies

* At least 1 GB of RAM is required for secure password-based key derivation with [scrypt](http://www.tarsnap.com/scrypt.html).
* We have tested `nucypher` with Windows, Mac OS, and GNU/Linux (GNU/Linux is recommended).
* If you don’t already have it, install [Python](https://www.python.org/downloads/). As of November 2019, we are working with Python 3.6, 3.7, and 3.8.

Before installing ``nucypher``, you may need to install necessary developer
tools and headers, if you don't have them already. In Ubuntu, Debian, Linux Mint
or similar distros:

    - libffi-dev
    - python3-dev
    - python3-pip
    - python3-virtualenv
    - build-essential
    - libssl-dev
        
Here's a one-liner to install the above packages on linux:
`sudo apt-get install python3-dev build-essential libffi-dev python3-pip`


## Standard Installation

`nucypher` can be installed by `pip` or `pipenv`, or run with `docker`.  
Ensure you have one of those installation tools installed for you system:

* [Pip Documentation](https://pip.pypa.io/en/stable/installing/)
* [Pipenv Documentation](https://pipenv.readthedocs.io/en/latest/)
* [Docker](https://docs.docker.com/install/)


### Pip Installation

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

    Before continuing, verify that your ``nucypher`` installation and entry points are functional;
    Activate your virtual environment (if you haven't already) and run the ``nucypher --help`` command in the console:

    ```bash
    nucypher --help
    ```

    You will see a list of possible usage options (``--version``, ``-v``, ``--dev``, etc.) and commands (``status``, ``ursula``, etc.).
    For example, you can use ``nucypher ursula destroy`` to delete all files associated with the node.


    In Python:

    ```python
    import nucypher
    ```

### Pipenv Installation


1. Install Application code with Pipenv

    Ensure you have `pipenv` installed (See full documentation for pipenv here: [Pipenv Documentation](https://pipenv.readthedocs.io/en/latest/)).
    Then to install `nucypher` with `pipenv`, run:

    ```bash
    $ pipenv install nucypher
    ```


2. Verify Installation

    In the console:

    ```bash
    $ nucypher --help
    ```

    In Python:

    ```python
   import nucypher
    ```

## Docker Installation

1. Install [Docker](https://docs.docker.com/install/)
2. (Optional) Follow these post install instructions: [https://docs.docker.com/install/linux/linux-postinstall/](https://docs.docker.com/install/linux/linux-postinstall/)
3. Get the latest nucypher image:

  `docker pull nucypher/nucypher:latest`

 Any nucypher CLI command can be executed in docker using the following syntax:
 
     docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 nucypher/nucypher:latest nucypher <ACTION> <OPTIONS>
  
  Examples:
    
  Display network stats:
    
     docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 nucypher/nucypher:latest nucypher status network --provider <PROVIDER URI> --network <NETWORK NAME>
    
        
  Running a pre-configured Worker as a daemon (See [Configuration Guide](/guides/network_node/ursula_configuration_guide)):
 
     docker run -d -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run

## Development Installation

Additional dependencies and setup steps are required to perform a "developer installation".
You do not need to perform these steps unless you intend to contribute a code or documentation change to 
the nucypher codebase.

Before continuing, ensure you have `git` installed ([Git Documentation](https://git-scm.com/doc)).


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

### Development Docker Installation
The intention of the Docker configurations in this directory is to enable anyone to develop and test NuCypher on all major operating systems with minimal prerequisites and installation hassle (tested on Ubuntu 16, MacOS 10.14, Windows 10).

#### Start with standard Docker Installation
1. Install [Docker](https://docs.docker.com/install/)
2. Install [Docker Compose](https://docs.docker.com/compose/install/)
3. `cd` to `dev/docker
4. Run `docker-compose up --build` **this must be done once to complete install**

#### Running NuCypher
Then you can do things like:
* Run the tests:
`docker-compose run nucypher-dev pytest`
* Start up an Ursula:
`docker-compose run nucypher-dev nucypher ursula run --dev --federated-only`
* Open a shell:
`docker-compose run nucypher-dev bash`

* Try some of the scripts in `dev/docker/scripts/`

From there you can develop, modify code, test as normal.

#### Other cases

* Run a network of 8 independent Ursulas
`docker-compose -f 8-federated-ursulas.yml up`
* Get the local ports these ursulas will be exposed on
`docker ps`
* To stop them...
 `docker-compose -f 8-federated-ursulas.yml stop`


## Systemd Service Installation

1. Use this template to create a file named `ursula.service` and place it in `/etc/systemd/system/`.

    ```
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
    ```

    Replace the following values with your own:

    * `<YOUR_USER>` - The host system's username to run the process with
    * `<YOUR WORKER ADDRESS PASSWORD>` - Worker's ETH account password
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
