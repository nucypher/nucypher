# NuCypher Federated Testnet (NuFT) Setup Guide

This guide is for individuals who intend to spin-up and maintain an Ursula node in the early stages of the NuFT while working with the NuCypher team to improve user experience, comfort, and code-quality of the NuCypher network.  Following the steps will launch a functioning federated-only Ursula node operating from a machine you control. Before getting started, please note: 

*WARNING The “NuCypher Federated Testnet” (NuFT) is an experimental pre-release of nucypher.  Expect bugs, downtime, and unannounced domain-wide restarts. NuFT nodes do not connect to any blockchain. Do not perform transactions on NuFT node addresses.*

Exiting the setup process at certain points prior to completion may lead to issues/bugs. 
If you encounter issues, we’d love to hear your feedback in our #staking channel on Discord (join by visiting https://discord.gg/7rmXa3s) or by opening an Issue on our GitHub (https://github.com/nucypher/nucypher/issues); Nonetheless, it’s recommended to initiate setup with the intention of completing all of the steps. 

- We encourage you to launch your node on a machine that is able to remain online with as few interruptions as possible, for as long as possible. Although it is possible to restart a node, excessive deactivation/reactivation can contribute to a lack of usable feedback from the test network. Additionally, node uptime will be important for proper functioning of Mainnet. Thus, it’s worthwhile to start working with a reliable machine now so that your nodes are compliant with our uptime requirements when the time comes.

- Setup requires knowledge of your machine’s public-facing IPv4 address and local network configuration. It advised to use a static IP address since changing IP addresses will require node reconfiguration. Configure port-forwarding rules on port 9151 if you are operating a node behind a firewall.  Once successfully up and running, your node will be discoverable by all other nodes in the test network.

- NuFT transmits application errors and crash reports to NuCypher’s sentry server.  This functionality is enabled by default for NuFT only and will be deactivated by default for mainnet.


### Overview

- Stage A - Install The Nucypher Environment
- Stage B -  Configure Ursula
- Stage C (Interactive Method) - Run the Node
- Stage C (System Service Method) - Run the Node

### Stage A | Install The Nucypher Environment

1) Install Python and Git

If you don’t already have them, install Python and git. 
As of November 2018, we are working with Python 3.6, 3.7, and 3.8. 

Official Python Website: https://www.python.org/downloads/ 
Git Install Guide: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git

2)  Create Virtual Environment

Create a system directory for the nucypher application code

`$ mkdir nucypher`

Create a virtual environment for your node to run in using virtualenv

```
$ virtualenv nucypher -p python3
...
```

Activate your virtual environment

```
$ source nucypher/bin/activate
...
(nucypher)$
```

3. Install Nucypher

Install nucypher with git and pip3 into your virtual environment

`(nucypher)$ pip3 install git+https://github.com/nucypher/nucypher.git@federated`

Re-activate your environment after installing

```
$ source nucypher/bin/activate
...
(nucypher)$ 
```


### Stage B | Configure Ursula

1. Verify that the installation was successful

Activate your virtual environment and run the nucypher --help command

```
$ source nucypher/bin/activate
...
(nucypher)$ nucypher --help
```

You will see a list of possible usage options (--version, -v, --dev, etc.) and commands (accounts, configure, deploy, etc.). For example, you can use nucypher configure destroy to delete all files associated with the node.

2. Configure a new Ursula node

```
(nucypher)$ nucypher configure install
...
```

3. Enter your public-facing IPv4 address when prompted

`Enter Node's Public IPv4 Address: <YOUR NODE IP HERE>`

4. Enter a password when prompted

`Enter a passphrase to encrypt your keyring: <YOUR PASSWORD HERE>`

Save your password as you will need it to relaunch the node, and please note:

- Minimum password length is 16 characters
- There is no password recovery process for NuFT nodes
- Do not use a password that you use anywhere else
- Your password may be displayed in logs or other recorded output.
- Security audits are ongoing on this codebase; for now, treat it as un-audited.


### Stage C | Run the Node (Interactive Method)

1. Connect to Testnet

NuCypher is maintaining a purpose-built endpoint to initially connect to the test network. To connect to the swarm run:

```
$(nucypher) nucypher ursula run --teacher-uri https://paris-load-balancer-14b0a87b7ff37a14.elb.eu-west-3.amazonaws.com
...
```

2. Verify Connection

This will drop your terminal session into the “Ursula Interactive Console” indicated by the >>>.  Verify that the node setup was successful by running the status command.

```
Ursula >>> status
...
```

To view a list of known nodes, execute the known_nodes command

```
Ursula >>> known_nodes 
...
```

You can also view your node’s network status webpage by navigating your web browser to https://<your-node-ip-address>:9151/status.  Since nodes self-sign TLS certificates, you may receive a warning from your web browser.

To stop your node from the interactive console and return to the terminal session

```
Ursula >>> stop    
...
```

Subsequent node restarts do not need the teacher endpoint specified.

```
(nucypher)$ nucypher ursula run 
...
```

Alternately you can run your node as a system service.
See the *“System Service Method”* section below.


### Stage C | Run the Node (System Service Method)
*NOTE - This is an alternative to the “Interactive Method”.*

1. Create Ursula System Service

Use this template to create a file named  ursula.service and place it in */etc/systemd/system/*.

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

Check Ursula service status

`$ sudo systemctl status ursula`
...

To restart your node service

`$ sudo systemctl restart ursula`

Updating Nucypher Application Code

Since Nucypher is under active development, you can expect frequent code changes to occur as bugs are discovered and code fixes are submitted. As a result, Ursula nodes will need to be frequently updated to use the most up-to-date version of the application code. The steps to update an Ursula running on NuFT are as follows and depends on the type of installation that was employed:

Stop the node 

Interactive method

`Ursula >>> stop`

OR

Systemd method

`$ sudo systemctl stop ursula`

2. Update to the latest code version

Update your virtual environment

`(nucypher)$ pip3 install git+https://github.com/nucypher/nucypher.git@federated`

3. Restart Ursula Node

Re-activate your environment after updating

Interactive method

```
$ source nucypher/bin/activate
...
(nucypher)$ nucypher ursula run
```

OR

Systemd Method

`$ sudo systemctl start ursula`

