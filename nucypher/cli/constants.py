"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.

"""


import os

import collections

import nucypher
from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    MinerEscrowDeployer,
    PolicyManagerDeployer,
    ContractDeployer
)


#
# Environment Variables
#
NUCYPHER_SENTRY_ENDPOINT = os.environ.get("NUCYPHER_SENTRY_ENDPOINT", "https://d8af7c4d692e4692a455328a280d845e@sentry.io/1310685")
LOG_TO_SENTRY = os.environ.get("NUCYPHER_SENTRY_LOGS", True)
LOG_TO_FILE = os.environ.get("NUCYPHER_FILE_LOGS", True)

KEYRING_PASSWORD_ENVVAR = "NUCYPHER_KEYRING_PASSWORD"


#
# Art
#
BANNER = """
                                  _               
                                 | |              
     _ __  _   _  ___ _   _ _ __ | |__   ___ _ __ 
    | '_ \| | | |/ __| | | | '_ \| '_ \ / _ \ '__|
    | | | | |_| | (__| |_| | |_) | | | |  __/ |   
    |_| |_|\__,_|\___|\__, | .__/|_| |_|\___|_|   
                       __/ | |                    
                      |___/|_|      
    version {}

""".format(nucypher.__version__)


#
# Deployers
#
DeployerInfo = collections.namedtuple('DeployerInfo', ('deployer_class',  # type: ContractDeployer
                                                       'upgradeable',     # type: bool
                                                       'agent_name',      # type: EthereumContractAgent
                                                       'dependant'))      # type: EthereumContractAgent
DEPLOYERS = collections.OrderedDict({

    NucypherTokenDeployer._contract_name: DeployerInfo(deployer_class=NucypherTokenDeployer,
                                                       upgradeable=False,
                                                       agent_name='token_agent',
                                                       dependant=None),

    MinerEscrowDeployer._contract_name: DeployerInfo(deployer_class=MinerEscrowDeployer,
                                                     upgradeable=True,
                                                     agent_name='miner_agent',
                                                     dependant='token_agent'),

    PolicyManagerDeployer._contract_name: DeployerInfo(deployer_class=PolicyManagerDeployer,
                                                       upgradeable=True,
                                                       agent_name='policy_agent',
                                                       dependant='miner_agent')
})
