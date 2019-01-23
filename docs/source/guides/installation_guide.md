# Installation Guide


## Standard Installation

We recommend installing nucypher with either `pip` or `pipenv`

### Standard Pip Installation

#### Create a Virtual Environment

```bash
$ virtualenv /your/path/nucypher-venv
...
```

Activate the newly created vrtual environment:

```bash
$ source /your/path/nucypher-venv
...
$(nucypher-venv)
```

#### Install Application Code with Pip

```bash
$(nucypher-venv) pip install nucypher
```

### Standard Pipenv Installation

See full documentation for pipenv here: [Pipenv Documentation](https://pipenv.readthedocs.io/en/latest/)

```bash
$ pipenv install nucypher
```


## Development Installation

### Acquire NuCypher Codebase

```bash
$ git clone https://github.com/nucypher/nucypher.git
...
$ cd nucypher
```

After acquiring a local copy of the application code, you will need to
install the project dependencies, we recommend using either `pip` or `pipenv`

### Pipenv Development Installation Method

```bash
$ pipenv install --dev --three --skip-lock --pre
...
$ pipenv shell
$(nucypher) pipenv run install-solc
...
```

### Pip Development Installation Method

```bash
$ pip install -e .[testing]
$ ./scripts/install_solc.sh
```

## System Service Installation

1. Use this template to create a file named  ursula.service and place it in */etc/systemd/system/*.

```
[Unit]
Description="Run 'Ursula', a NuCypher Staking Node."

[Service]
User=<YOUR USER>
Type=simple
Environment="NUCYPHER_KEYRING_PASSPHRASE=<YOUR PASSPHRASE>"
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

```bash
$ sudo systemctl enable ursula
...
```

3. Run Ursula System Service

To start Ursula services using systemd

```bash
$ sudo systemctl start ursula
...
```

4. Check Ursula service status

```bash
$ sudo systemctl status ursula
...
```

5. To restart your node service

```bash
$ sudo systemctl restart ursula
```
