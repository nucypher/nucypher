#### single command line worker deployment

1. follow the instructions here https://docs.nucypher.com/en/latest/guides/staking_guide.html

2. provision ubuntu hosts accessible from the internet and to which you can ssh into.
    * if you need to use a .pem file, use the "amazon" example

3. modify the contents of [inventory.yml](inventory.yml) to add your worker addresses, staker addresses, and passwords, as well as the addresses of your host(s)

4. from /nucypher/deploy/ansible/worker run `ansible-playbook worker/setup_remote_workers.yml -i worker/inventory.yml -l cassandra`


#### single command line worker UPDATE

updates all your existing nodes to the latest nucypher docker image

1. from /nucypher/deploy/ansible/worker run `ansible-playbook worker/update_remote_workers.yml -i worker/inventory.yml -l cassandra`