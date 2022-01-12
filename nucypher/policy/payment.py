from abc import ABC, abstractmethod
from typing import Optional

import maya

from nucypher.blockchain.eth.agents import PolicyManagerAgent, SubscriptionManagerAgent
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.utils import get_current_period, datetime_at_period, calculate_period_duration
from nucypher_core import ReencryptionRequest
from nucypher.policy.policies import BlockchainPolicy
from hexbytes import HexBytes
from nucypher.blockchain.economics import EconomicsFactory


class ReencryptionPrerequisite(ABC):
    """Baseclass for reencryption preconditions relating to a policy."""

    ONCHAIN = NotImplemented

    @abstractmethod
    def verify(self, node: 'Ursula', request: ReencryptionRequest) -> bool:
        """returns True is reencryption is permitted by ursula for the given reencryption request."""
        raise NotImplemented


class PaymentMethod(ReencryptionPrerequisite, ABC):
    # TODO: Logging?

    @abstractmethod
    def pay(self, policy: BlockchainPolicy) -> HexBytes:
        raise NotImplemented

    @abstractmethod
    def default_rate(self):
        raise NotImplemented

    @abstractmethod
    def calculate_price(self,
                        shares: int,
                        duration: int = None,
                        expiration: maya.MayaDT = None,
                        value: Optional[int] = None,
                        rate: Optional[int] = None
                        ) -> dict:
        raise NotImplemented

    @abstractmethod
    def validate_rate(self, shares: int, value: int, duration: int) -> None:
        raise NotImplemented


class ContractPayment(PaymentMethod, ABC):
    """Baseclass for on-chain policy payment; Requires a blockchain connection."""

    ONCHAIN = True
    _AGENT = NotImplemented

    def __init__(self, provider: str, network: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.network = network
        self.registry = InMemoryContractRegistry.from_latest_publication(network=network)
        self.economics = EconomicsFactory.get_economics(registry=self.registry)
        self.__agent = None  # delay blockchain/registry reads until later

    @property
    def agent(self):
        if self.__agent:
            return self.__agent  # get cache
        agent = self._AGENT(provider_uri=self.provider, registry=self.registry)
        self.__agent = agent
        return self.__agent  # set cache


class FreeReencryptions(PaymentMethod):
    """Useful for private federations and testing."""

    ONCHAIN = False

    def verify(self, node: 'Ursula', request: ReencryptionRequest) -> bool:
        return True

    def pay(self, policy: BlockchainPolicy) -> HexBytes:
        return HexBytes(bytes())

    def default_rate(self) -> int:
        return 0

    def calculate_price(self, *args, **kwargs) -> dict:
        return dict(value=0, rate=0)

    def validate_rate(self, *args, **kwargs) -> None:
        return


class PolicyManagerPayment(ContractPayment):
    """Handle policy payment using the PolicyManager contract."""

    _AGENT = PolicyManagerAgent

    def verify(self, node, request: ReencryptionRequest) -> bool:
        """Verify policy payment by reading the PolicyManager contract"""
        arrangements = self.agent.fetch_policy_arrangements(policy_id=bytes(request.hrac))
        members = set()
        for arrangement in arrangements:
            members.add(arrangement.node)
            if node.checksum_address == arrangement.node:
                return True
        else:
            if not members:
                return False
            return False

    def pay(self, policy: BlockchainPolicy) -> HexBytes:
        """Writes a new policy to the PolicyManager contract."""
        receipt = self.agent.create_policy(
            value=policy.value,                     # wei
            policy_id=bytes(policy.hrac),           # bytes16 _policyID
            end_timestamp=policy.expiration.epoch,  # uint16 _numberOfPeriods
            node_addresses=policy.addresses,        # address[] memory _nodes
            transacting_power=policy.publisher.transacting_power
        )

        # Capture transaction receipt
        txid = receipt['transactionHash']
        policy.log.info(f"published policy TXID: {txid}")
        return txid

    def default_rate(self):
        _minimum, default, _maximum = self.agent.get_fee_rate_range()
        return default

    def validate_rate(self, shares: int, value: int, duration: int) -> None:
        rate_per_period = value // shares // duration  # wei
        recalculated_value = duration * rate_per_period * shares
        if recalculated_value != value:
            raise ValueError(f"Invalid policy value calculation - "
                             f"{value} can't be divided into {shares} staker payments per period "
                             f"for {duration} periods without a remainder")

    def calculate_price(self,
                        shares: int,
                        duration: int = None,
                        expiration: maya.MayaDT = None,
                        value: Optional[int] = None,
                        rate: Optional[int] = None) -> dict:

        # Check for negative inputs
        if sum(True for i in (shares, duration, value, rate) if i is not None and i < 0) > 0:
            raise BlockchainPolicy.InvalidPolicyValue(f"Negative policy parameters are not allowed. Be positive.")

        # Check for policy params
        if not (bool(value) ^ bool(rate)):
            if not (value == 0 or rate == 0):  # Support a min fee rate of 0
                raise BlockchainPolicy.InvalidPolicyValue(f"Either 'value' or 'rate'  must be provided for policy. "
                                                          f"Got value: {value} and rate: {rate}")
            
        if duration:
            # Duration equals one period means that expiration date is the last second of the current period
            current_period = get_current_period(seconds_per_period=self.economics.seconds_per_period)
            expiration = datetime_at_period(current_period + duration,
                                            seconds_per_period=self.economics.seconds_per_period,
                                            start_of_period=True)
            expiration -= 1  # Get the last second of the target period
        else:
            now = self.agent.blockchain.get_blocktime()
            duration = calculate_period_duration(now=maya.MayaDT(now),
                                                 future_time=expiration,
                                                 seconds_per_period=self.economics.seconds_per_period)
            duration += 1  # Number of all included periods

        if value is None:
            value = rate * duration * shares

        else:
            value_per_node = value // shares
            if value_per_node * shares != value:
                raise BlockchainPolicy.InvalidPolicyValue(f"Policy value of ({value} wei) cannot be"
                                                          f" divided by N ({shares}) without a remainder.")

            rate = value_per_node // duration
            if rate * duration != value_per_node:
                raise BlockchainPolicy.InvalidPolicyValue(f"Policy value of ({value_per_node} wei) per node "
                                                          f"cannot be divided by duration ({duration} periods)"
                                                          f" without a remainder.")

        params = dict(rate=rate, value=value, duration=duration)
        return params


class SubscriptionManagerPayment(ContractPayment):
    """Handle policy payment using the SubscriptionManager contract."""

    _AGENT = SubscriptionManagerAgent

    def verify(self, node: 'Ursula', request: ReencryptionRequest) -> bool:
        """Verify policy payment by reading the SubscriptionManager contract"""
        result = self.agent.is_policy_active(policy_id=bytes(request.hrac))
        return result

    def pay(self, policy: BlockchainPolicy) -> HexBytes:
        """Writes a new policy to the SubscriptionManager contract."""

        # TODO: Make this optional on-chain
        commencement = policy.commencement or self.agent.blockchain.get_blocktime()

        receipt = self.agent.create_policy(
            value=policy.value,                     # wei
            policy_id=bytes(policy.hrac),           # bytes16 _policyID
            start_timestamp=commencement,           # uint16
            end_timestamp=policy.expiration.epoch,  # uint16
            transacting_power=policy.publisher.transacting_power
        )

        # Capture transaction receipt
        txid = receipt['transactionHash']
        policy.log.info(f"published policy TXID: {txid}")
        return txid

    def default_rate(self) -> int:
        fixed_rate = self.agent.rate_per_second()
        return fixed_rate

    def calculate_price(self,
                        shares: int,
                        duration: int = None,
                        commencement: maya.MayaDT = None,
                        expiration: maya.MayaDT = None,
                        value: Optional[int] = None,
                        rate: Optional[int] = None
                        ) -> dict:
        # TODO: This section needs improvement but works for basic cases.

        if rate:
            raise ValueError(f"{self._AGENT.contract_name} uses a fixed rate.")
        if not any((duration, expiration, value)):
            raise ValueError("Policy end time must be specified with 'expiration', 'duration' or 'value'.")

        # Check for negative inputs
        if sum(True for i in (shares, duration, value) if i is not None and i < 0) > 0:
            raise ValueError(f"Negative policy parameters are not allowed. Be positive.")

        if not duration:
            if expiration and commencement:
                duration = expiration - commencement
            if not commencement:
                # TODO: This is inaccurate since the on-chain policy creation is slightly in the future
                commencement = maya.now()
            if expiration and not duration:
                duration = expiration.epoch - commencement.epoch

        subscription_rate = self.agent.rate_per_second()
        value = subscription_rate * duration
        params = dict(rate=subscription_rate, value=value, duration=duration)
        return params

    def validate_rate(self, shares: int, value: int, duration: int) -> None:
        subscription_rate = self.agent.rate_per_second()
        if value and duration:
            if duration != value // subscription_rate:
                raise ValueError(f"Invalid duration ({duration}) for value ({value}).")
            if value != duration * subscription_rate:
                raise ValueError(f"Invalid value ({value}) for duration ({duration}).")


PAYMENT_METHODS = {
    'Free': FreeReencryptions,
    'PolicyManager': PolicyManagerPayment,
    'SubscriptionManager': SubscriptionManagerPayment,
}
