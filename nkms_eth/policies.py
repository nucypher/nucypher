from collections import OrderedDict
from typing import Tuple, List

from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner
from nkms_eth.token import NuCypherKMSToken


class PolicyArrangement:
    def __init__(self, author: 'PolicyAuthor', miner: 'Miner', value: int=None,
                 periods: int=None, rate: int=None, arrangement_id: bytes=None):

        if arrangement_id is None:
            self.id = self.__class__._generate_arrangement_id()  # TODO: Generate policy ID

        # The relationship between two addresses
        self.author = author
        self.policy_manager = author.policy_manager

        self.miner = miner

        # Arrangement value, rate, and duration
        if (value and periods) and (not rate):
            rate = value // periods
        self._rate = rate
        self.value = value
        self.periods = periods  # TODO: datetime -> duration in blocks

        self.is_published = False
        self._elapsed_periods = None
        self.publish_transaction = None    # TX hashes set when published to network
        self.revoke_transaction = None

    @staticmethod
    def _generate_arrangement_id(policy_hrac: bytes) -> bytes:
        pass  # TODO

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(client={}, node={})"
        r = r.format(class_name, self.author, self.miner)
        return r

    def publish(self, gas_price: int) -> str:

        payload = {'from': self.author.address,
                   'value': self.value,
                   'gas_price': gas_price}

        txhash = self.policy_manager.transact(payload).createPolicy(self.id,
                                                                    self.miner.address,
                                                                    self.periods)

        self.policy_manager.blockchain._chain.wait.for_receipt(txhash)
        self.publish_transaction = txhash
        self.is_published = True
        return txhash

    def __update_periods(self) -> None:
        blockchain_record = self.policy_manager.fetch_arrangement_data(self.id)
        client, delegate, rate, *periods = blockchain_record
        self._elapsed_periods = periods

    def revoke(self, gas_price: int) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""
        txhash = self.policy_manager.revoke_arrangement(self.id, author=self.author, gas_price=gas_price)
        self.revoke_transaction = txhash
        return txhash


class PolicyManager:

    __contract_name = 'PolicyManager'

    class ContractDeploymentError(Exception):
        pass

    def __init__(self, escrow: Escrow):
        self.escrow = escrow
        self.token = escrow.token
        self.blockchain = self.token.blockchain

        self.armed = False
        self.__contract = None

    @property
    def is_deployed(self):
        return bool(self.__contract is not None)

    def arm(self) -> None:
        self.armed = True

    def deploy(self) -> Tuple[str, str]:
        if self.armed is False:
            raise PolicyManager.ContractDeploymentError('PolicyManager contract not armed')
        if self.is_deployed is True:
            raise PolicyManager.ContractDeploymentError('PolicyManager contract already deployed')
        if self.escrow._contract is None:
            raise Escrow.ContractDeploymentError('Escrow contract must be deployed before')
        if self.token.contract is None:
            raise NuCypherKMSToken.ContractDeploymentError('Token contract must be deployed before')

        # Creator deploys the policy manager
        the_policy_manager_contract, deploy_txhash = self.blockchain._chain.provider.deploy_contract(
            self.__contract_name,
            deploy_args=[self.escrow._contract.address],
            deploy_transaction={'from': self.token.creator})

        self.__contract = the_policy_manager_contract

        set_txhash = self.escrow.transact({'from': self.token.creator}).setPolicyManager(the_policy_manager_contract.address)
        self.blockchain._chain.wait.for_receipt(set_txhash)

        return deploy_txhash, set_txhash

    def __call__(self, *args, **kwargs):
        return self.__contract.call()

    @classmethod
    def get(cls, escrow: Escrow) -> 'PolicyManager':
        contract = escrow.blockchain._chain.provider.get_contract(cls.__contract_name)
        instance = cls(escrow)
        instance.__contract = contract
        return instance

    def transact(self, *args):
        """Transmit a network transaction."""
        return self.__contract.transact(*args)

    def fetch_arrangement_data(self, arrangement_id: bytes) -> list:
        blockchain_record = self.__call__().policies(arrangement_id)
        return blockchain_record

    def revoke_arrangement(self, arrangement_id: bytes, author: 'PolicyAuthor', gas_price: int):
        """
        Revoke by arrangement ID.
        Only the policy author can revoke the policy
        """
        txhash = self.transact({'from': author.address, 'gas_price': gas_price}).revokePolicy(arrangement_id)
        self.blockchain._chain.wait.for_receipt(txhash)
        return txhash


class PolicyAuthor:
    def __init__(self, address: bytes, policy_manager: PolicyManager):

        if policy_manager.is_deployed is False:
            raise PolicyManager.ContractDeploymentError('PolicyManager contract not deployed.')
        self.policy_manager = policy_manager

        if isinstance(address, bytes):
            address = address.hex()
        self.address = address

        self._arrangements = OrderedDict()    # Track authored policies by id

    def make_arrangement(self, delegate: str, periods: int, rate: int, arrangement_id: bytes=None) -> PolicyArrangement:
        """
        Create a new arrangement to carry out a blockchain policy for the specified rate and time.
        """

        value = rate * periods
        arrangement = PolicyArrangement(author=self,
                                        delegate_address=delegate,
                                        value=value,
                                        periods=periods)

        self._arrangements[arrangement.id] = {arrangement_id: arrangement}
        return arrangement

    def get_arrangement(self, arrangement_id: bytes) -> PolicyArrangement:
        """Fetch a published arrangement from the blockchain"""

        blockchain_record = self.policy_manager().policies(arrangement_id)
        client, delegate, rate, *periods = blockchain_record

        arrangement = PolicyArrangement(author=self, delegate_address=delegate, rate=rate)

        arrangement._elapsed_periods = periods
        arrangement.is_published = True
        return arrangement

    def revoke_arrangement(self, arrangement_id):
        """Lookup the arrangement in the cache and revoke it on the blockchain"""
        try:
            arrangement = self._arrangements[arrangement_id]
        except KeyError:
            raise Exception('No such arrangement')
        else:
            txhash = arrangement.revoke()
        return txhash

    def select_miners(self, quantity: int) -> List[str]:
        miner_addresses = self.policy_manager.escrow.sample(quantity=quantity)
        return miner_addresses

