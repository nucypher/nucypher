# Deploying Nucypher (worker/staker) to Azure Cloud


### Instances Provisioning Playbooks for Azure

If you have Ansible setup to run playbooks against the Azure resource API then you can run the `deploy_nucypher_azure_infra.yml`


### Setting up your Ubuntu environment for running Ansible Azure

You have 3 options for using Ansible to deploy your infrastructure:

1. Utilize the "cloud shell" within the Azure portal which comes pre-installed with Ansible and your credentials.
2. Use your own copy of Ansible and install the Azure module (through pip)
3. Setup your own deployment machine on Ubuntu to run playbooks and deploy stakers/workers.

Option 1 is ready to go, use the play book `deploy_nucypher_azure_infra.yml` followed by the playbooks in the /worker/ folder

For options 2 you will need Ansible (Azure module) installed on your local host (documentation [here](https://docs.ansible.com/ansible/latest/scenario_guides/guide_azure.html)).

For option 3 I've included the following steps below to setup a vanilla Ubuntu node to run Ansible (w/ Azure module), geth, and everything you need to deploy the Ansible playbooks for your Nucypher staker/workers.

(Instructions valid w/ Canonical Ubuntu 16.04/18.04)


#### Install virtualenv and activate
```console
azureuser@ncdeploy:~$ sudo apt-get update
azureuser@ncdeploy:~$ sudo apt-get install -y virtualenv
azureuser@ncdeploy:~$ virtualenv nucypher_ansible
azureuser@ncdeploy:~$ source nucypher_ansible/bin/activate
```
#### Install Ansible (w/ Azure module) inside a virtual environment
```console
azureuser@ncdeploy:~$ pip install 'ansible[azure]'
```
#### Export environment variables (Azure credentials)
```console
azureuser@ncdeploy:~$ export AZURE_CLIENT_ID=''
azureuser@ncdeploy:~$ export AZURE_SECRET=''
azureuser@ncdeploy:~$ export AZURE_SUBSCRIPTION_ID=''
azureuser@ncdeploy:~$ export AZURE_TENANT=''
```
#### Create 2GB swap file (for local geth instance)
```console
azureuser@ncdeploy:~$ sudo fallocate -l 2G /swapfile
azureuser@ncdeploy:~$ sudo chmod 600 /swapfile
azureuser@ncdeploy:~$ sudo mkswap /swapfile
azureuser@ncdeploy:~$ sudo swapon /swapfile
azureuser@ncdeploy:~$ sudo cp /etc/fstab /etc/fstab.bak
azureuser@ncdeploy:~$ echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
#### Install geth
```console
azureuser@ncdeploy:~$ sudo add-apt-repository -y ppa:ethereum/ethereum
azureuser@ncdeploy:~$ sudo apt-get update
azureuser@ncdeploy:~$ sudo apt-get install -y ethereum
```
#### Run geth (goerli testnet)
```console
azureuser@ncdeploy:~$ nohup geth --goerli --syncmode fast --cache 1024 &
```
#### Check geth is finished syncing
```console
azureuser@ncdeploy:~$ geth attach ~/.ethereum/goerli/geth.ipc
(within geth): eth.syncing
```
Wait for the result from above to come back as false

#### Run ansible playbook to deploy Nucypher Staker and Worker(s)

<ins>Inventory values:</ins>
* Azure Location: West Central US (typcially one of the lowest cost locations)
* Linux Distribution: Ubuntu 18.04 LTS
* VM Size: B1s (1 vCPU , 1GB RAM, 4GB Ephemeral Disk)
* Make sure to update the inventory file with your public key for login.

```console
azureuser@ncdeploy:~$ ansible-playbook deploy_nucypher_azure_infra.yml -i inventory.yml
```
