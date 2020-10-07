"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import copy
import os
import re
import json
import maya
import time
from base64 import b64encode
from jinja2 import Template
import requests

from ansible.playbook import Playbook
from ansible.parsing.dataloader import DataLoader
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.inventory.manager import InventoryManager
from ansible.plugins.callback import CallbackBase
from ansible.vars.manager import VariableManager
from ansible.playbook.play import Play
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible import context as ansible_context
from ansible.module_utils.common.collections import ImmutableDict

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.blockchain.eth.clients import PUBLIC_CHAINS
from nucypher.blockchain.eth.networks import NetworksInventory

NODE_CONFIG_STORAGE_KEY = 'worker-configs'
URSULA_PORT = 9151
PROMETHEUS_PORTS = [9101]


ansible_context.CLIARGS = ImmutableDict(
    {
        'syntax': False,
        'start_at_task': None,
        'verbosity': 0,
        'become_method': 'sudo'
    }
)

class AnsiblePlayBookResultsCollector(CallbackBase):
    """

    """

    def __init__(self, sock, *args, return_results=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.playbook_results = []
        self.sock = sock
        self.results = return_results

    def v2_playbook_on_play_start(self, play):
        name = play.get_name().strip()
        if not name:
            msg = '\nPLAY {}\n'.format('*' * 100)
        else:
            msg = '\nPLAY [{}] {}\n'.format(name, '*' * 100)
        self.send_save(msg)

    def v2_playbook_on_task_start(self, task, is_conditional):
        msg = '\nTASK [{}] {}\n'.format(task.get_name(), '*' * 100)
        self.send_save(msg)

    def v2_runner_on_ok(self, result, *args, **kwargs):
        if result.is_changed():
            data = '[{}]=> changed'.format(result._host.name)
        else:
            data = '[{}]=> ok'.format(result._host.name)
        self.send_save(data, color='yellow' if result.is_changed() else 'green')
        if 'msg' in result._task_fields['args']:
            msg = result._task_fields['args']['msg']
            self.send_save(msg, color='yellow')
            self.send_save('\n')
            if self.results:
                for k in self.results.keys():
                    regex = fr'{k}:\s*(?P<data>.*)'
                    match = re.search(regex, msg, flags=re.MULTILINE)
                    if match:
                        self.results[k].append((result._host.name, match.groupdict()['data']))


    def v2_runner_on_failed(self, result, *args, **kwargs):
        if 'changed' in result._result:
            del result._result['changed']
        data = 'fail: [{}]=> {}: {}'.format(result._host.name, 'failed',
                                                                            self._dump_results(result._result))
        self.send_save(data, color='red')

    def v2_runner_on_unreachable(self, result):
        if 'changed' in result._result:
            del result._result['changed']
        data = '[{}]=> {}: {}'.format(result._host.name, 'unreachable',
                                                                            self._dump_results(result._result))
        self.send_save(data)

    def v2_runner_on_skipped(self, result):
        if 'changed' in result._result:
            del result._result['changed']
        data = '[{}]=> {}: {}'.format(
            result._host.name,
            'skipped',
            self._dump_results(result._result)
        )
        self.send_save(data, color='blue')

    def v2_playbook_on_stats(self, stats):
        hosts = sorted(stats.processed.keys())
        data = '\nPLAY RECAP {}\n'.format('*' * 100)
        self.send_save(data)
        for h in hosts:
            s = stats.summarize(h)
            msg = '{} : ok={} changed={} unreachable={} failed={} skipped={}'.format(
                h, s['ok'], s['changed'], s['unreachable'], s['failures'], s['skipped'])
            self.send_save(msg)

    def send_save(self, data, color=None):
        self.sock.echo(data, color=color)
        self.playbook_results.append(data)


class BaseCloudNodeConfigurator:

    PROMETHEUS_PORT = PROMETHEUS_PORTS[0]

    def __init__(self,
        emitter,
        stakeholder,
        stakeholder_config_path,
        blockchain_provider=None,
        nucypher_image=None,
        seed_network=False,
        sentry_dsn=None,
        profile=None,
        prometheus=False,
        ):

        self.emitter = emitter
        self.stakeholder = stakeholder
        self.config_filename = f'{self.stakeholder.network}.json'
        self.network = self.stakeholder.network
        self.created_new_nodes = False

        # the keys in this dict are used as search patterns by the anisble result collector and it will return
        # these values for each node if it happens upon them in some output
        self.output_capture = {'worker address': [], 'rest url': [], 'nucypher version': [], 'nickname': []}

        # where we save our state data so we can remember the resources we created for future use
        self.config_path = os.path.join(DEFAULT_CONFIG_ROOT, NODE_CONFIG_STORAGE_KEY, self.config_filename)

        self.emitter.echo(f"cloudworker config path: {self.config_path}")

        if os.path.exists(self.config_path):
            self.config = json.load(open(self.config_path))
            self.namespace = self.config['namespace']
        else:
            self.namespace = f'{self.stakeholder.network}-{maya.now().date.isoformat()}'
            self.config = {
                "namespace": self.namespace,
                "keyringpassword": b64encode(os.urandom(64)).decode('utf-8'),
                "ethpassword": b64encode(os.urandom(64)).decode('utf-8'),
            }
            configdir = os.path.dirname(self.config_path)
            os.makedirs(configdir, exist_ok=True)

        # configure provider specific attributes
        self._configure_provider_params(profile)

        # if certain config options have been specified with this invocation,
        # save these to update host specific variables before deployment
        # to allow for individual host config differentiation
        self.host_level_overrides = {
            'blockchain_provider': blockchain_provider,
            'nucypher_image': nucypher_image,
            'sentry_dsn': sentry_dsn
        }

        self.config['blockchain_provider'] = blockchain_provider or self.config.get('blockchain_provider') or f'/root/.local/share/geth/.ethereum/{self.chain_name}/geth.ipc' # the default for nodes that run their own geth container
        self.config['nucypher_image'] = nucypher_image or self.config.get('nucypher_image') or 'nucypher/nucypher:latest'
        self.config['sentry_dsn'] = sentry_dsn or self.config.get('sentry_dsn')
        self.config['seed_network'] = seed_network or self.config.get('seed_network')
        if not self.config['seed_network']:
            self.config.pop('seed_node', None)
        self.nodes_are_decentralized = 'geth.ipc' in self.config['blockchain_provider']
        self.config['stakeholder_config_file'] = stakeholder_config_path
        self.config['use-prometheus'] = prometheus

        self._write_config()

    def _write_config(self):
        with open(self.config_path, 'w') as outfile:
            json.dump(self.config, outfile, indent=4)

    @property
    def _provider_deploy_attrs(self):
        return []

    def _configure_provider_params(self, provider_profile):
        pass

    def _do_setup_for_instance_creation(self):
        pass

    @property
    def chain_id(self):
        return NetworksInventory.get_ethereum_chain_id(self.network)

    @property
    def chain_name(self):
        try:
            return PUBLIC_CHAINS[self.chain_id].lower()
        except KeyError:
            self.emitter.echo(f"could not identify public blockchain for {self.network}", color="red")

    @property
    def inventory_path(self):
        return os.path.join(DEFAULT_CONFIG_ROOT, NODE_CONFIG_STORAGE_KEY, f'{self.namespace}.ansible_inventory.yml')

    def generate_ansible_inventory(self, staker_addresses, wipe_nucypher=False):

        status_template = Template(self._inventory_template)

        inventory_content = status_template.render(
            deployer=self,
            nodes=[value for key, value in self.config['instances'].items() if key in staker_addresses],
            wipe_nucypher=wipe_nucypher
        )


        with open(self.inventory_path, 'w') as outfile:
            outfile.write(inventory_content)
        self._write_config()

        return self.inventory_path

    def create_nodes_for_stakers(self, stakers):
        count = len(stakers)
        self.emitter.echo(f"ensuring cloud nodes exist for the following {count} stakers:")
        for s in stakers:
            self.emitter.echo(f'\t{s}')
        time.sleep(3)
        self._do_setup_for_instance_creation()

        if not self.config.get('instances'):
            self.config['instances'] = {}

        for address in stakers:
            existing_node = self.config['instances'].get(address)
            if not existing_node:
                self.emitter.echo(f'creating new node for {address}', color='yellow')
                time.sleep(3)
                node_data = self.create_new_node_for_staker(address)
                node_data['provider'] = self.provider_name
                self.config['instances'][address] = node_data
                if self.config['seed_network'] and not self.config.get('seed_node'):
                    self.config['seed_node'] = node_data['publicaddress']
                self._write_config()
                self.created_new_nodes = True

        return self.config

    @property
    def _inventory_template(self):
        return open(os.path.join(os.path.dirname(__file__), 'templates', 'cloud_deploy_ansible_inventory.j2'), 'r').read()

    def deploy_nucypher_on_existing_nodes(self, staker_addresses, wipe_nucypher=False):

        # first update any specified input in our node config
        for k, input_specified_value in self.host_level_overrides.items():
            for address in staker_addresses:
                if self.config['instances'].get(address):
                    # if an instance already has a specified value, we only override
                    # it if that value was input for this command invocation
                    if input_specified_value:
                        self.config['instances'][address][k] = input_specified_value
                    elif not self.config['instances'][address].get(k):
                        self.config['instances'][address][k] = self.config[k]

                    self._write_config()

        if self.created_new_nodes:
            self.emitter.echo("--- Giving newly created nodes some time to get ready ----")
            time.sleep(30)
        self.emitter.echo('Running ansible deployment for all running nodes.', color='green')

        self.emitter.echo(f"using inventory file at {self.inventory_path}", color='yellow')
        if self.config.get('keypair_path'):
            self.emitter.echo(f"using keypair file at {self.config['keypair_path']}", color='yellow')

        self.generate_ansible_inventory(staker_addresses, wipe_nucypher=wipe_nucypher)

        results = self.output_capture
        loader = DataLoader()
        inventory = InventoryManager(loader=loader, sources=self.inventory_path)
        callback = AnsiblePlayBookResultsCollector(sock=self.emitter, return_results=self.output_capture)
        variable_manager = VariableManager(loader=loader, inventory=inventory)

        executor = PlaybookExecutor(
            playbooks = ['deploy/ansible/worker/setup_remote_workers.yml'],
            inventory=inventory,
            variable_manager=variable_manager,
            loader=loader,
            passwords=dict(),
        )
        executor._tqm._stdout_callback = callback
        executor.run()

        self.update_captured_instance_data(self.output_capture)
        self.give_helpful_hints()


    def get_worker_status(self, staker_addresses):

        self.emitter.echo('Running ansible status playbook.', color='green')
        self.emitter.echo('If something goes wrong, it is generally safe to ctrl-c and run the previous command again.')

        self.emitter.echo(f"using inventory file at {self.inventory_path}", color='yellow')
        if self.config.get('keypair_path'):
            self.emitter.echo(f"using keypair file at {self.config['keypair_path']}", color='yellow')


        self.generate_ansible_inventory(staker_addresses)

        loader = DataLoader()
        inventory = InventoryManager(loader=loader, sources=self.inventory_path)
        callback = AnsiblePlayBookResultsCollector(sock=self.emitter, return_results=self.output_capture)
        variable_manager = VariableManager(loader=loader, inventory=inventory)

        executor = PlaybookExecutor(
            playbooks = ['deploy/ansible/worker/get_workers_status.yml'],
            inventory=inventory,
            variable_manager=variable_manager,
            loader=loader,
            passwords=dict(),
        )
        executor._tqm._stdout_callback = callback
        executor.run()
        self.update_captured_instance_data(self.output_capture)

        self.give_helpful_hints()

    def get_provider_hosts(self):
        return [
            (address, host_data) for address, host_data in self.config['instances'].items()
            if host_data['provider'] == self.provider_name
        ]

    def destroy_resources(self, staker_addresses=None):
        addresses = [s for s in staker_addresses if s in self.get_provider_hosts()]
        if self._destroy_resources(addresses):
            self.emitter.echo(f"deleted all requested resources for {self.provider_name}.  We are clean.  No money is being spent.", color="green")

    def _destroy_resources(self):
        raise NotImplementedError

    def update_captured_instance_data(self, results):
        instances_by_public_address = {d['publicaddress']: d for d in self.config['instances'].values()}
        for k, data in results.items():
            # results are keyed by 'publicaddress' in config data
            for instance_address, value in data:
                instances_by_public_address[instance_address][k] = value

        for k, v in self.config['instances'].items():
            if instances_by_public_address.get(v['publicaddress']):
                self.config['instances'][k] = instances_by_public_address.get(v['publicaddress'])

        self._write_config()
        self.update_stakeholder_config()

    def update_stakeholder_config(self):
        data = {}
        data = json.loads(open(self.config['stakeholder_config_file'], 'r').read())
        existing_worker_data = data.get('worker_data', {})
        existing_worker_data.update(self.config['instances'])
        data['worker_data'] = existing_worker_data
        with open(self.config['stakeholder_config_file'], 'w') as outfile:
            json.dump(data, outfile, indent=4)

    def give_helpful_hints(self):

        if self.config.get('keypair_path'):
            keypair = self.config['keypair_path']
            self.emitter.echo(f'ssh into any node using `ssh ubuntu@<node address> -i "{keypair}"`', color="yellow")

class DigitalOceanConfigurator(BaseCloudNodeConfigurator):

    default_region = 'SFO3'
    provider_name = 'digitalocean'

    @property
    def instance_size(self):
        if self.nodes_are_decentralized:
            return 's-2vcpu-4gb'
        return "s-1vcpu-2gb"

    @property
    def _provider_deploy_attrs(self):
        return [
            {'key': 'default_user', 'value': 'root'},
        ]

    def _configure_provider_params(self, provider_profile):
        self.token = os.getenv('DIGITALOCEAN_ACCESS_TOKEN')
        if not self.token:
            self.emitter.echo(f"Please `export DIGITALOCEAN_ACCESS_TOKEN=<your access token.>` from here:  https://cloud.digitalocean.com/account/api/tokens", color="red")
            raise AttributeError("Could not continue without DIGITALOCEAN_ACCESS_TOKEN environment variable.")
        self.region = os.getenv('DIGITALOCEAN_REGION') or self.config.get('region')
        if not self.region:
            self.region = self.default_region
        self.config['region'] = self.region
        self.emitter.echo(f'using DigitalOcean region: {self.region}, to change regions `export DIGITALOCEAN_REGION: https://www.digitalocean.com/docs/platform/availability-matrix/', color='yellow')

        self.sshkey = os.getenv('DIGITAL_OCEAN_KEY_FINGERPRINT') or self.config.get('sshkey')
        if not self.sshkey:
            self.emitter.echo("Please set the name of your Digital Ocean SSH Key (`export DIGITAL_OCEAN_KEY_FINGERPRINT=<your preferred ssh key fingerprint>` from here: https://cloud.digitalocean.com/account/security", color="red")
            self.emitter.echo("it should look like `DIGITAL_OCEAN_KEY_FINGERPRINT=88:fb:53:51:09:aa:af:02:e2:99:95:2d:39:64:c1:64`", color="red")
            raise AttributeError("Could not continue without DIGITAL_OCEAN_KEY_FINGERPRINT environment variable.")
        self.config['sshkey'] = self.sshkey

        self._write_config()

    def create_new_node_for_staker(self, address):

        response = requests.post("https://api.digitalocean.com/v2/droplets",
            {
                "name": f'{self.namespace}-{address}',
                "region": self.region,
                "size": self.instance_size,
                "image":"ubuntu-20-04-x64",
                "ssh_keys": [self.sshkey]
            },
            headers = {
                "Authorization": f'Bearer {self.token}'
            }
        )

        if response.status_code < 300:
            resp = response.json()

            new_node_id = resp['droplet']['id']
            node_data = {'InstanceId': new_node_id}

            self.emitter.echo("\twaiting for instance to come online...")

            instance_ip = None
            while not instance_ip:
                time.sleep(1)

                instance_resp = requests.get(
                    f'https://api.digitalocean.com/v2/droplets/{new_node_id}/',
                    headers = {
                        "Authorization": f'Bearer {self.token}'
                    }
                ).json().get('droplet')
                if instance_resp['status'] == 'active':
                    if instance_resp.get('networks', {}).get('v4'):
                        instance_ip = instance_resp['networks']['v4'][0]['ip_address']
            node_data['publicaddress'] = instance_ip
            node_data['remote_provider'] = self.config.get('blockchain_provider')
            node_data['provider_deploy_attrs']= self._provider_deploy_attrs
            return node_data

        else:
            self.emitter.echo(response.text, color='red')
            raise BaseException("Error creating resources in DigitalOcean")

    def _destroy_resources(self, stakes):

        existing_instances = copy.copy(self.config.get('instances'))
        if existing_instances:
            for address, instance in existing_instances.items():
                if stakes and not address in stakes:
                    continue
                self.emitter.echo(f"deleting worker instance for {address} in 3 seconds...", color='red')
                time.sleep(3)
                if requests.delete(
                    f'https://api.digitalocean.com/v2/droplets/{instance["InstanceId"]}/',
                    headers = {
                        "Authorization": f'Bearer {self.token}'
                }).status_code == 204:
                    self.emitter.echo(f"\tdestroyed instance for {address}")
                    del self.config['instances'][address]
                    self._write_config()
                else:
                    raise

        return True



class AWSNodeConfigurator(BaseCloudNodeConfigurator):

    """
    gets a node up and running.
    """

    provider_name = 'aws'
    EC2_INSTANCE_SIZE = 't3.small'

    # TODO: this probably needs to be region specific...
    EC2_AMI = 'ami-09dd2e08d601bff67'
    preferred_platform = 'ubuntu-focal' #unused

    @property
    def _provider_deploy_attrs(self):
        return [
            {'key': 'ansible_ssh_private_key_file', 'value': self.config['keypair_path']},
            {'key': 'default_user', 'value': 'ubuntu'}
        ]

    def _configure_provider_params(self, provider_profile):

        # some attributes we will configure later
        self.vpc = None

        # if boto3 is not available, inform the user they'll need it.
        try:
            import boto3
        except ImportError:
            self.emitter.echo("You need to have boto3 installed to use this feature (pip3 install boto3)", color='red')
            raise AttributeError("boto3 not found.")
        # figure out which AWS account to use.

        # find aws profiles on user's local environment
        profiles = boto3.session.Session().available_profiles

        self.profile = provider_profile or self.config.get('profile')
        if not self.profile:
            self.emitter.echo("Aws nodes can only be created with an aws profile. (https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html)", color='red')
            raise AttributeError("AWS profile not configured.")
        self.emitter.echo(f'using profile: {self.profile}')
        if self.profile in profiles:
            self.session = boto3.Session(profile_name=self.profile)
            self.ec2Client = self.session.client('ec2')
            self.ec2Resource = self.session.resource('ec2')
        else:
            if profiles:
                self.emitter.echo(f"please select a profile (--aws-profile) from your aws profiles: {profiles}", color='red')
            else:
                self.emitter.echo(f"no aws profiles could be found. Ensure aws is installed and configured: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html", color='red')
        if self.profile:
            self.config['profile'] = self.profile

        self.keypair = self.config.get('keypair')
        if not self.keypair:
            self.keypair, keypair_path = self._create_keypair()
            self.config['keypair_path'] = keypair_path

        self.config['keypair'] = self.keypair

    @property
    def aws_tags(self):
        # to keep track of the junk we put in the cloud
        return [{"Key": "Name", "Value": self.namespace}]

    def _create_keypair(self):
        new_keypair_data = self.ec2Client.create_key_pair(KeyName=f'{self.namespace}')
        outpath = os.path.join(DEFAULT_CONFIG_ROOT, NODE_CONFIG_STORAGE_KEY, f'{self.namespace}.awskeypair')
        os.makedirs(os.path.dirname(outpath), exist_ok=True)
        with open(outpath, 'w') as outfile:
            outfile.write(new_keypair_data['KeyMaterial'])
        # set local keypair permissions https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html
        os.chmod(outpath, 0o400)
        self.emitter.echo(f"a new aws keypair was saved to {outpath}, keep it safe.", color='yellow')
        return new_keypair_data['KeyName'], outpath

    def _delete_keypair(self):
        # only use self.namespace here to avoid accidental deletions of pre-existing keypairs
        deleted_keypair_data = self.ec2Client.delete_key_pair(KeyName=f'{self.namespace}')
        if deleted_keypair_data['HTTPStatusCode'] == 200:
            outpath = os.path.join(DEFAULT_CONFIG_ROOT, NODE_CONFIG_STORAGE_KEY, f'{self.namespace}.awskeypair')
            os.remove(outpath)
            self.emitter.echo(f"keypair at {outpath}, was deleted", color='yellow')

    def _ensure_vpc(self):
        """creates an aws virtual private cloud if one doesn't exist"""

        try:
            from botocore import exceptions as botoexceptions
        except ImportError:
            self.emitter.echo("You need to have boto3 installed to use this feature (pip3 install boto3)")
            return

        if not self.vpc:
            vpc_id = self.config.get('Vpc')
            if vpc_id:
                self.vpc = self.ec2Resource.Vpc(vpc_id)
            else:
                try:
                    vpcdata = self.ec2Client.create_vpc(CidrBlock='172.16.0.0/16')
                except botoexceptions.NoCredentialsError:
                    raise ValueError(f'Could create AWS resource with profile "{self.profile}" and keypair "{self.keypair}", please run this command with --aws-profile and --aws-keypair to specify matching aws credentials')
                self.vpc = self.ec2Resource.Vpc(vpcdata['Vpc']['VpcId'])
                self.vpc.wait_until_available()
                self.vpc.create_tags(Tags=self.aws_tags)
                self.vpc.modify_attribute(EnableDnsSupport = { 'Value': True })
                self.vpc.modify_attribute(EnableDnsHostnames = { 'Value': True })
                self.config['Vpc'] = vpc_id = self.vpc.id
                self._write_config()
        return self.vpc

    def _configure_path_to_internet(self):
        """
            create and configure all the little AWS bits we need to get an internet request
            from the internet to our node and back
        """

        if not self.config.get('InternetGateway'):
            gatewaydata = self.ec2Client.create_internet_gateway()
            self.config['InternetGateway'] = gateway_id = gatewaydata['InternetGateway']['InternetGatewayId']
            # tag it
            self._write_config()
            self.ec2Resource.InternetGateway(
                self.config['InternetGateway']).create_tags(Tags=self.aws_tags)

            self.vpc.attach_internet_gateway(InternetGatewayId=self.config['InternetGateway'])

        routetable_id = self.config.get('RouteTable')
        if not routetable_id:
            routetable = self.vpc.create_route_table()
            self.config['RouteTable'] = routetable_id = routetable.id
            self._write_config()
            routetable.create_tags(Tags=self.aws_tags)

        routetable = self.ec2Resource.RouteTable(routetable_id)
        routetable.create_route(DestinationCidrBlock='0.0.0.0/0', GatewayId=self.config['InternetGateway'])

        if not self.config.get('Subnet'):
            subnetdata = self.ec2Client.create_subnet(CidrBlock='172.16.1.0/24', VpcId=self.vpc.id)
            self.config['Subnet'] = subnet_id = subnetdata['Subnet']['SubnetId']
            self._write_config()
            self.ec2Resource.Subnet(subnet_id).create_tags(Tags=self.aws_tags)

        routetable.associate_with_subnet(SubnetId=self.config['Subnet'])

        if not self.config.get('SecurityGroup'):
            securitygroupdata = self.ec2Client.create_security_group(GroupName=f'Ursula-{self.namespace}', Description='ssh and Nucypher ports', VpcId=self.config['Vpc'])
            self.config['SecurityGroup'] = sg_id = securitygroupdata['GroupId']
            self._write_config()
            securitygroup = self.ec2Resource.SecurityGroup(sg_id)
            securitygroup.create_tags(Tags=self.aws_tags)

            securitygroup.authorize_ingress(CidrIp='0.0.0.0/0', IpProtocol='tcp', FromPort=22, ToPort=22)
            # TODO: is it always 9151?  Does that matter? Should this be configurable?
            securitygroup.authorize_ingress(CidrIp='0.0.0.0/0', IpProtocol='tcp', FromPort=URSULA_PORT, ToPort=URSULA_PORT)
            for port in PROMETHEUS_PORTS:
                securitygroup.authorize_ingress(CidrIp='0.0.0.0/0', IpProtocol='tcp', FromPort=port, ToPort=port)

    def _do_setup_for_instance_creation(self):
        if not getattr(self, 'profile', None):
            self.emitter.echo("Aws nodes can only be created with an aws profile. (https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html)", color='red')
            raise AttributeError("AWS profile not configured.")

        self.emitter.echo("ensuring that prerequisite cloud resources exist for instance creation.")
        self._ensure_vpc()
        self._configure_path_to_internet()
        self.emitter.echo("all prerequisite cloud resources do exist.")

    def _destroy_resources(self, stakes):
        try:
            from botocore import exceptions as botoexceptions
        except ImportError:
            self.emitter.echo("You need to have boto3 installed to use this feature (pip3 install boto3)")
            return

        vpc = self.ec2Resource.Vpc(self.config['Vpc'])
        if self.config.get('instances'):
            for address, instance in self.config['instances'].items():
                if stakes and not address in stakes:
                    continue
                self.emitter.echo(f"deleting worker instance for {address} in 3 seconds...", color='red')
                time.sleep(3)
                self.ec2Resource.Instance(instance['InstanceId']).terminate()
                del self.config['instances'][address]
                self._write_config()

        if not self.config.instances:
            self.emitter.echo("waiting for instance termination...")
            time.sleep(10)
            for subresource in ['Subnet', 'RouteTable', 'SecurityGroup']:
                tries = 0
                while self.config.get(subresource) and tries < 10:
                    try:
                        getattr(self.ec2Resource, subresource)(self.config[subresource]).delete()
                        self.emitter.echo(f'deleted {subresource}: {self.config[subresource]}')
                        del self.config[subresource]
                        self._write_config()
                    except botoexceptions.ClientError as e:
                        tries += 1
                        self.emitter.echo(f'failed to delete {subresource}, because: {e}.. trying again in 10...', color="yellow")
                        time.sleep(10)
                if tries > 10:
                    self.emitter.echo("some resources could not be deleted because AWS is taking awhile to delete things.  Run this command again in a minute or so...", color="yellow")
                    return False

            if self.config.get('InternetGateway'):
                self.ec2Resource.InternetGateway(self.config['InternetGateway']).detach_from_vpc(VpcId=self.config['Vpc'])
                self.ec2Resource.InternetGateway(self.config['InternetGateway']).delete()
                self.emitter.echo(f'deleted InternetGateway: {self.config["InternetGateway"]}')
                del self.config['InternetGateway']
            self._write_config()

            if self.config.get('Vpc'):
                vpc.delete()
                self.emitter.echo(f'deleted Vpc: {self.config["Vpc"]}')
                del self.config['Vpc']

            if self.config.get('keypair'):
                self.emitter.echo(f'deleting keypair {self.keypair} in 5 seconds...', color='red')
                time.sleep(6)
                self.ec2Client.delete_key_pair(KeyName=self.config.get('keypair'))
                del self.config['keypair']
                os.remove(self.config['keypair_path'])

        return True

    def create_new_node_for_staker(self, address):
        new_instance_data = self.ec2Client.run_instances(
            ImageId=self.EC2_AMI,
            InstanceType=self.EC2_INSTANCE_SIZE,
            MaxCount=1,
            MinCount=1,
            KeyName=self.keypair,
            NetworkInterfaces=[
                {
                    'AssociatePublicIpAddress': True,
                    'DeleteOnTermination': True,
                    'DeviceIndex': 0,
                    'Groups': [
                        self.config['SecurityGroup']
                    ],
                    'SubnetId': self.config['Subnet'],
                },
            ],
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': f'{self.namespace}-{address}'
                        },
                    ]
                },
            ],
        )

        node_data = {'InstanceId': new_instance_data['Instances'][0]['InstanceId']}

        instance = self.ec2Resource.Instance(new_instance_data['Instances'][0]['InstanceId'])
        self.emitter.echo("\twaiting for instance to come online...")
        instance.wait_until_running()
        instance.load()
        node_data['publicaddress'] = instance.public_dns_name
        node_data['provider_deploy_attrs']= self._provider_deploy_attrs

        return node_data

class GenericConfigurator(BaseCloudNodeConfigurator):

    provider_name = 'generic'

    def create_nodes_for_stakers(self, stakers, host_address, login_name, key_path, ssh_port):

        if not self.config.get('instances'):
            self.config['instances'] = {}

        for address in stakers:
            node_data = self.config['instances'].get(address, {})
            if node_data:
                self.emitter.echo(f"Host info already exists for staker {address}; Updating and proceeding.", color="yellow")
                time.sleep(3)

            node_data['publicaddress'] = host_address
            node_data['provider'] = self.provider_name
            node_data['provider_deploy_attrs'] = [
                {'key': 'ansible_ssh_private_key_file', 'value': key_path},
                {'key': 'default_user', 'value': login_name},
                {'key': 'ansible_port', 'value': ssh_port}
            ]

            self.config['instances'][address] = node_data
            if self.config['seed_network'] and not self.config.get('seed_node'):
                self.config['seed_node'] = node_data['publicaddress']
            self._write_config()
            self.created_new_nodes = True

        return self.config



class CloudDeployers:

    aws = AWSNodeConfigurator
    digitalocean = DigitalOceanConfigurator
    generic = GenericConfigurator

    @staticmethod
    def get_deployer(name):
        return getattr(CloudDeployers, name)
