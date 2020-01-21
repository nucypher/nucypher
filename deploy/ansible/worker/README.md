#### single command line worker deployment

1. follow the instructions here https://docs.nucypher.com/en/latest/guides/staking_guide.html

2. provision ubuntu hosts accessible from the internet

3. modify the contents of [inventory.yml](inventory.yml) to add your worker addresses, staker addresses, and passwords, as well as the addresses of your host(s)

4. from /nucypher/deploy/ansible/worker run `ansible-playbook worker/setup_remote_worker.yml -i worker/inventory.yml -l cassandra`