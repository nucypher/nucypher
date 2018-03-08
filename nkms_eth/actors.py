from collections import OrderedDict
from typing import Tuple, List

# from nkms_eth.agents import MinerAgent, PolicyAgent
from nkms_eth.base import Actor


class PolicyArrangement:
    def __init__(self, author: 'PolicyAuthor', miner: 'Miner', value: int,
                 periods: int, arrangement_id: bytes=None):

        if arrangement_id is None:
            self.id = self.__class__._generate_arrangement_id()  # TODO: Generate policy ID

        # The relationship exists between two addresses
        self.author = author
        self.policy_agent = author.policy_agent

        self.miner = miner

        # Arrangement value, rate, and duration
        rate = value // periods
        self._rate = rate

        self.value = value
        self.periods = periods  # TODO: datetime -> duration in blocks

        self.is_published = False

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

        txhash = self.policy_agent.transact(payload).createPolicy(self.id,
                                                                    self.miner.address,
                                                                    self.periods)

        self.policy_agent._blockchain._chain.wait.for_receipt(txhash)
        self.publish_transaction = txhash
        self.is_published = True
        return txhash

    def __update_periods(self) -> None:
        blockchain_record = self.policy_agent.fetch_arrangement_data(self.id)
        client, delegate, rate, *periods = blockchain_record
        self._elapsed_periods = periods

    def revoke(self, gas_price: int) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""
        txhash = self.policy_agent.revoke_arrangement(self.id, author=self.author, gas_price=gas_price)
        self.revoke_transaction = txhash
        return txhash


class Miner(Actor):
    """
    Practically carrying a pickaxe.
    Intended for use as an Ursula mixin.

    Accepts a running blockchain, deployed token contract, and deployed escrow contract.
    If the provided token and escrow contracts are not deployed,
    ContractDeploymentError will be raised.

    """

    def __init__(self, miner_agent, address):
        super().__init__(address)

        self.miner_agent = miner_agent
        miner_agent.miners.append(self)    # Track Miners

        self._token_agent = miner_agent._token
        self._blockchain = self._token_agent._blockchain

        self._transactions = list()
        self._locked_tokens = self._update_locked_tokens()

    def _update_locked_tokens(self) -> None:
        self._locked_tokens = self.miner_agent.call().getLockedTokens(self.address)
        return None

    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self._token_agent.transact({'from': self.address}).approve(self.miner_agent._contract.address, amount)
        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        self._transactions.append(txhash)

        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.transact({'from': self.address}).deposit(amount, locktime)
        self._blockchain._chain.wait.for_receipt(deposit_txhash, timeout=self._blockchain._timeout)

        self._transactions.append(deposit_txhash)

        return deposit_txhash

    @property
    def is_staking(self):
        return bool(self._locked_tokens > 0)

    def lock(self, amount: int, locktime: int) -> Tuple[str, str, str]:
        """Deposit and lock tokens for mining."""

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        lock_txhash = self.miner_agent.transact({'from': self.address}).switchLock()
        self._blockchain._chain.wait.for_receipt(lock_txhash, timeout=self._blockchain._timeout)

        self._transactions.extend([approve_txhash, deposit_txhash, lock_txhash])

        return approve_txhash, deposit_txhash, lock_txhash

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.miner_agent.transact({'from': self.address}).confirmActivity()
        self._blockchain._chain.wait.for_receipt(txhash)

        self._transactions.append(txhash)

        return txhash

    def mint(self) -> str:
        """Computes and transfers tokens to the miner's account"""

        txhash = self.miner_agent.transact({'from': self.address}).mint()
        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        self._transactions.append(txhash)

        return txhash

    def collect_policy_reward(self, policy_manager) -> str:
        """Collect policy reward in ETH"""

        txhash = policy_manager.transact({'from': self.address}).withdraw()
        self._blockchain._chain.wait.for_receipt(txhash)

        self._transactions.append(txhash)

        return txhash

    def publish_miner_id(self, miner_id) -> str:
        """Store a new Miner ID"""

        txhash = self.miner_agent.transact({'from': self.address}).setMinerId(miner_id)
        self._blockchain._chain.wait.for_receipt(txhash)

        self._transactions.append(txhash)

        return txhash

    def fetch_miner_ids(self) -> tuple:
        """Retrieve all stored Miner IDs on this miner"""

        count = self.escrow().getMinerInfo(self.escrow.MinerInfoField.MINER_IDS_LENGTH.value,
                                           self.address,
                                           0).encode('latin-1')

        count = self._blockchain._chain.web3.toInt(count)

        miner_ids = list()
        for index in range(count):
            miner_id = self.miner_agent.call().getMinerInfo(self.escrow.MinerInfoField.MINER_ID.value, self.address, index)
            encoded_miner_id = miner_id.encode('latin-1')  # TODO change when v4 of web3.py is released
            miner_ids.append(encoded_miner_id)

        return tuple(miner_ids)

    def eth_balance(self):
        return self._blockchain._chain.web3.eth.getBalance(self.address)

    def token_balance(self) -> int:
        """Check miner's current token balance"""

        # self._token_agent._check_contract_deployment()
        balance = self._token_agent.call().balanceOf(self.address)

        return balance

    def withdraw(self, amount: int=0, entire_balance=False) -> str:
        """Withdraw tokens"""

        tokens_amount = self._blockchain._chain.web3.toInt(
            self.escrow().getMinerInfo(self.escrow.MinerInfoField.VALUE.value, self.address, 0).encode('latin-1'))

        txhash = self.escrow.transact({'from': self.address}).withdraw(tokens_amount)

        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        if entire_balance and amount:
            raise Exception("Specify an amount or entire balance, not both")

        if entire_balance:
            txhash = self.escrow.transact({'from': self.address}).withdraw(tokens_amount)
        else:
            txhash = self.escrow.transact({'from': self.address}).withdraw(amount)

        self._transactions.append(txhash)
        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        return txhash


class PolicyAuthor(Actor):
    """Alice"""

    def __init__(self, address: bytes, policy_agent):
        self.policy_agent = policy_agent
        super().__init__(address)
        self._arrangements = OrderedDict()    # Track authored policies by id

    def make_arrangement(self, miner: Miner, periods: int, rate: int, arrangement_id: bytes=None) -> PolicyArrangement:
        """
        Create a new arrangement to carry out a blockchain policy for the specified rate and time.
        """

        value = rate * periods
        arrangement = PolicyArrangement(author=self,
                                        miner=miner,
                                        value=value,
                                        periods=periods)

        self._arrangements[arrangement.id] = {arrangement_id: arrangement}
        return arrangement

    def get_arrangement(self, arrangement_id: bytes) -> PolicyArrangement:
        """Fetch a published arrangement from the blockchain"""

        blockchain_record = self.policy_agent.call().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.policy_agent.miner_agent)
        arrangement = PolicyArrangement(author=self, miner=miner, periods=duration)

        arrangement.is_published = True
        return arrangement

    def revoke_arrangement(self, arrangement_id):
        """Lookup the arrangement in the cache and revoke it on the blockchain"""
        try:
            arrangement = self._arrangements[arrangement_id]
        except KeyError:
            raise Exception('No such arrangement')  #TODO
        else:
            txhash = arrangement.revoke()
        return txhash

    def recruit(self, quantity: int) -> List[str]:
        miner_addresses = self.policy_agent.miner_agent.sample(quantity=quantity)
        return miner_addresses

    def balance(self):
        return self.policy_agent.miner_agent.call().balanceOf(self.address)

