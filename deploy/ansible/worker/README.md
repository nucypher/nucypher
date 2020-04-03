#### single command line worker deployment

1. provision ubuntu hosts accessible from the internet and to which you can ssh into.
    * if you need to use a .pem file, use the "amazon" example (in /nucypher/deploy/ansible/worker/inventory.yml)

2. if you would like to pre-create your worker accounts, use a locally running geth instance to create accounts for the workers you'll be deploying (you will need the keystores), otherwise worker accounts you can have workers created automatically as the nodes are deployed

3. follow the instructions here https://docs.nucypher.com/en/latest/guides/network_node/staking_guide.html

4. modify the contents of [inventory.yml](inventory.yml) to add your worker addresses, staker addresses, and passwords, as well as the addresses of your host(s) and save it somewhere

5. ensure that you have installed nucypher with development tools. `pip install -r dev-requirements.txt`

6. from /nucypher/deploy/ansible/worker run `ansible-playbook worker/setup_remote_workers.yml -i ~/my-gemini-nodes.yml`

#### single command line worker UPDATE

updates all your existing nodes to the latest nucypher docker image

1. from `/nucypher/deploy/ansible/` run `ansible-playbook worker/update_remote_workers.yml -i ~/my-gemini-nodes.yml`


#### other commands to try

* `ansible-playbook worker/get_workers_status.yml -i ~/my-gemini-nodes.yml`
   * prints out some useful information about your nodes
