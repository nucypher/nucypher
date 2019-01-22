# Installation Guide

## Pip Installation

`pip install nucypher`

## Pipenv Installation

`pipenv install nucypher`

## Development Installation

### Acquire NuCypher Codebase

```
git clone https://github.com/nucypher/nucypher.git  # clone NuCypher repository
cd nucypher
```

### Pipenv

```
pipenv install --dev --three --skip-lock --pre
pipenv shell
```

### Pip

```
pip install -e .[testing]
```

## System Service Installation

1. Use this template to create a file named  ursula.service and place it in */etc/systemd/system/*.

`/etc/systemd/system/ursula.service`

```
[Unit]
Description="Run 'Ursula', a NuCypher Staking Node."

[Service]
User=<YOUR USER>
Type=simple
Environment="NUCYPHER_KEYRING_PASSPHRASE=<YOUR PASSPHRASE>"
ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run --teacher-uri https://paris-load-balancer-14b0a87b7ff37a14.elb.eu-west-3.amazonaws.com

[Install]
WantedBy=multi-user.target
```

2. Enable Ursula System Service

```
$ sudo systemctl enable ursula
...
```

3. Run Ursula System Service

To start Ursula services using systemd

```
$ sudo systemctl start ursula
...
```

4. Check Ursula service status

```
$ sudo systemctl status ursula
...
```

5. To restart your node service

`$ sudo systemctl restart ursula`

Updating Nucypher Application Code
