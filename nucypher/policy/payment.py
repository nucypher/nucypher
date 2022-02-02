from abc import ABC, abstractmethod
from typing import Optional, NamedTuple, Dict

import maya
from hexbytes import HexBytes
from nucypher_core import ReencryptionRequest
from web3.types import Wei, ChecksumAddress, Timestamp, TxReceipt

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import PolicyManagerAgent, SubscriptionManagerAgent
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.utils import get_current_period, datetime_at_period, calculate_period_duration
from nucypher.policy.policies import BlockchainPolicy, Policy


class ReencryptionPrerequisite(ABC):
    """Baseclass for reencryption preconditions relating to a policy."""

    ONCHAIN = NotImplemented
    NAME = NotImplemented

    @abstractmethod
    def verify(self, payee: ChecksumAddress, request: ReencryptionRequest) -> bool:
        """returns True if reencryption is permitted by the payee (ursula) for the given reencryption request."""
        raise NotImplemented


class PaymentMethod(ReencryptionPrerequisite, ABC):
    """Extends ReencryptionPrerequisite to facilitate policy payment and payment verification."""

    class Quote(NamedTuple):
        rate: int
        value: int
        commencement: int  # epoch
        expiration: int    # epoch
        duration: int      # seconds or periods

    @abstractmethod
    def pay(self, policy: Policy) -> Dict:
        """Carry out payment for the given policy."""
        raise NotImplemented

    @property
    @abstractmethod
    def rate(self) -> int:
        """The cost of this payment method per unit."""
        raise NotImplemented

    @abstractmethod
    def quote(self,
              shares: int,
              duration: Optional[int] = None,
              commencement: Optional[Timestamp] = None,
              expiration: Optional[int] = None,
              value: Optional[int] = None,
              rate: Optional[int] = None
              ) -> Quote:
        """Generates a valid quote for this payment method using pricing details."""
        raise NotImplemented

    @abstractmethod
    def validate_price(self,
                       shares: int,
                       value: int,
                       duration: int) -> None:
        raise NotImplemented


class ContractPayment(PaymentMethod, ABC):
    """Baseclass for on-chain policy payment; Requires a blockchain connection."""

    ONCHAIN = True
    _AGENT = NotImplemented

    class Quote(PaymentMethod.Quote):
        rate: Wei
        value: Wei

    def __init__(self, provider: str, network: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.network = network
        self.registry = InMemoryContractRegistry.from_latest_publication(network=network)
        self.__agent = None  # delay blockchain/registry reads until later

    @property
    def agent(self):
        """Returns an instance of the agent used to carry out contract payments."""
        if self.__agent:
            return self.__agent  # get cache
        agent = self._AGENT(provider_uri=self.provider, registry=self.registry)
        self.__agent = agent
        return self.__agent  # set cache


class FreeReencryptions(PaymentMethod):
    """Useful for private federations and testing."""

    ONCHAIN = False
    NAME = 'Free'

    def verify(self, payee: ChecksumAddress, request: ReencryptionRequest) -> bool:
        return True

    def pay(self, policy: Policy) -> Dict:
        receipt = f'Receipt for free policy {bytes(policy.hrac).hex()}.'
        return dict(receipt=receipt.encode())

    @property
    def rate(self) -> int:
        return 0

    def quote(self,
              commencement: Optional[Timestamp] = None,
              expiration: Optional[Timestamp] = None,
              duration: Optional[int] = None,
              *args, **kwargs
              ) -> PaymentMethod.Quote:
        return self.Quote(
            value=0,
            rate=0,
            duration=duration,
            commencement=commencement,
            expiration=expiration
        )

    def validate_price(self, *args, **kwargs) -> bool:
        return True


class PolicyManagerPayment(ContractPayment):
    """Handle policy payment using the PolicyManager contract."""

    _AGENT = PolicyManagerAgent
    NAME = 'PolicyManager'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.economics = EconomicsFactory.get_economics(registry=self.registry, provider_uri=self.provider)

    def verify(self, payee: ChecksumAddress, request: ReencryptionRequest) -> bool:
        """Verify policy payment by reading the PolicyManager contract"""
        arrangements = self.agent.fetch_policy_arrangements(policy_id=bytes(request.hrac))
        members = set()
        for arrangement in arrangements:
            members.add(arrangement.node)
            if payee == arrangement.node:
                return True
        else:
            if not members:
                return False
            return False

    def pay(self, policy: BlockchainPolicy) -> HexBytes:
        """Writes a new policy to the PolicyManager contract."""
        receipt = self.agent.create_policy(
            value=policy.value,                # wei
            policy_id=bytes(policy.hrac),      # bytes16 _policyID
            end_timestamp=policy.expiration,   # uint16 _numberOfPeriods
            node_addresses=policy.nodes,       # address[] memory _nodes
            transacting_power=policy.publisher.transacting_power
        )
        return receipt

    @property
    def rate(self) -> Wei:
        """Returns the default rate set on PolicyManager."""
        _minimum, default, _maximum = self.agent.get_fee_rate_range()
        return default

    def validate_price(self, shares: int, value: int, duration: int) -> bool:
        rate_per_period = value // shares // duration  # wei
        recalculated_value = duration * rate_per_period * shares
        if recalculated_value != value:
            raise ValueError(f"Invalid policy value calculation - "
                             f"{value} can't be divided into {shares} staker payments per period "
                             f"for {duration} periods without a remainder")
        return True

    def quote(self,
              shares: int,
              expiration: Optional[Timestamp] = None,
              duration: Optional[int] = None,
              value: Optional[int] = None,
              rate: Optional[int] = None,
              *args, **kwargs
              ) -> PaymentMethod.Quote:

        # Check for negative inputs
        if sum(True for i in (shares, expiration, duration, value, rate) if i is not None and i < 0) > 0:
            raise ValueError(f"Negative policy parameters are not allowed. Be positive.")

        # Check for policy params
        if not (bool(value) ^ bool(rate)):
            if not (value == 0 or rate == 0):  # Support a min fee rate of 0
                raise ValueError(f"Either 'value' or 'rate'  must be provided for policy. "
                                 f"Got value: {value} and rate: {rate}")

        now = self.agent.blockchain.get_blocktime()
        if duration:
            # Duration equals one period means that expiration date is the last second of the current period
            current_period = get_current_period(seconds_per_period=self.economics.seconds_per_period)
            expiration = datetime_at_period(current_period + duration,
                                            seconds_per_period=self.economics.seconds_per_period,
                                            start_of_period=True)
            expiration -= 1  # Get the last second of the target period
        else:
            duration = calculate_period_duration(now=maya.MayaDT(now),
                                                 future_time=maya.MayaDT(expiration),
                                                 seconds_per_period=self.economics.seconds_per_period)
            duration += 1  # Number of all included periods

        if value is None:
            value = rate * duration * shares

        else:
            value_per_node = value // shares
            if value_per_node * shares != value:
                raise ValueError(f"Policy value of ({value} wei) cannot be "
                                 f"divided by N ({shares}) without a remainder.")

            rate = value_per_node // duration
            if rate * duration != value_per_node:
                raise ValueError(f"Policy value of ({value_per_node} wei) per node "
                                 f"cannot be divided by duration ({duration} periods)"
                                 f" without a remainder.")
        q = self.Quote(
            rate=Wei(rate),
            value=Wei(value),
            duration=duration,
            expiration=Timestamp(expiration),
            commencement=Timestamp(now)
        )
        return q


class SubscriptionManagerPayment(ContractPayment):
    """Handle policy payment using the SubscriptionManager contract."""

    _AGENT = SubscriptionManagerAgent
    NAME = 'SubscriptionManager'

    def verify(self, payee: ChecksumAddress, request: ReencryptionRequest) -> bool:
        """Verify policy payment by reading the SubscriptionManager contract"""
        result = self.agent.is_policy_active(policy_id=bytes(request.hrac))
        return result

    def pay(self, policy: BlockchainPolicy) -> TxReceipt:
        """Writes a new policy to the SubscriptionManager contract."""
        receipt = self.agent.create_policy(
            value=policy.value,                   # wei
            policy_id=bytes(policy.hrac),         # bytes16 _policyID
            start_timestamp=policy.commencement,  # uint16
            end_timestamp=policy.expiration,      # uint16
            transacting_power=policy.publisher.transacting_power
        )
        return receipt

    @property
    def rate(self) -> Wei:
        fixed_rate = self.agent.rate_per_second()
        return Wei(fixed_rate)

    def quote(self,
              commencement: Optional[Timestamp] = None,
              expiration: Optional[Timestamp] = None,
              duration: Optional[int] = None,
              value: Optional[Wei] = None,
              rate: Optional[Wei] = None,
              *args, **kwargs
              ) -> PaymentMethod.Quote:
        """
        A quote for the SubscriptionManager is calculated as rate * duration seconds
        """
        # TODO: This section is over-complicated and needs improvement but works for basic cases.

        # invalid input
        if rate:
            raise ValueError(f"{self._AGENT.contract_name} uses a fixed rate.")
        if not any((duration, expiration, value)):
            raise ValueError("Policy end time must be specified with 'expiration', 'duration' or 'value'.")
        if sum(True for i in (commencement, expiration, duration, value, rate) if i is not None and i < 0) > 0:
            raise ValueError(f"Negative policy parameters are not allowed. Be positive.")

        if not commencement:
            if expiration and duration:
                commencement = expiration - duration  # reverse
            else:
                commencement = maya.now().epoch  # start now

        if not duration:
            if expiration and commencement:
                duration = expiration - commencement

        q = self.Quote(
            rate=Wei(self.rate),
            value=Wei(self.rate * duration),
            commencement=Timestamp(commencement),
            expiration=Timestamp(expiration),
            duration=duration
        )
        return q

    def validate_price(self, value: Wei, duration: Wei, *args, **kwargs) -> bool:
        if value and duration:
            if duration != value // self.rate:
                raise ValueError(f"Invalid duration ({duration}) for value ({value}).")
            if value != duration * self.rate:
                raise ValueError(f"Invalid value ({value}) for duration ({duration}).")
        return True


PAYMENT_METHODS = {
    FreeReencryptions.NAME: FreeReencryptions,
    PolicyManagerPayment.NAME: PolicyManagerPayment,
    SubscriptionManagerPayment.NAME: SubscriptionManagerPayment,
}
