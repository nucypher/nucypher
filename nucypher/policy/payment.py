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


from abc import ABC, abstractmethod
from typing import Optional, NamedTuple, Dict

import maya
from nucypher_core import ReencryptionRequest
from web3.types import Wei, Timestamp, TxReceipt, ChecksumAddress

from nucypher.blockchain.eth.agents import SubscriptionManagerAgent
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, BaseContractRegistry
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
        shares: int

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

    def __init__(self,
                 eth_provider: str,
                 network: str,
                 registry: Optional[BaseContractRegistry] = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = eth_provider
        self.network = network
        if not registry:
            registry = InMemoryContractRegistry.from_latest_publication(network=network)
        self.registry = registry
        self.__agent = None  # delay blockchain/registry reads until later

    @property
    def agent(self):
        """Returns an instance of the agent used to carry out contract payments."""
        if self.__agent:
            return self.__agent  # get cache
        agent = self._AGENT(eth_provider_uri=self.provider, registry=self.registry)
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
              shares: int,
              commencement: Optional[Timestamp] = None,
              expiration: Optional[Timestamp] = None,
              duration: Optional[int] = None,
              *args, **kwargs
              ) -> PaymentMethod.Quote:
        return self.Quote(
            value=0,
            rate=0,
            shares=shares,
            duration=duration,
            commencement=commencement,
            expiration=expiration
        )

    def validate_price(self, *args, **kwargs) -> bool:
        return True


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
            size=len(policy.kfrags),              # uint16
            start_timestamp=policy.commencement,  # uint16
            end_timestamp=policy.expiration,      # uint16
            transacting_power=policy.publisher.transacting_power
        )
        return receipt

    @property
    def rate(self) -> Wei:
        fixed_rate = self.agent.fee_rate()
        return Wei(fixed_rate)

    def quote(self,
              shares: int,
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
            value=Wei(self.rate * duration * shares),
            shares=shares,
            commencement=Timestamp(commencement),
            expiration=Timestamp(expiration),
            duration=duration
        )
        return q

    def validate_price(self, value: Wei, duration: Wei, shares: int, *args, **kwargs) -> bool:
        expected_price = Wei(shares * duration * self.rate)
        if value != expected_price:
            raise ValueError(f"Policy value ({value}) doesn't match expected value ({expected_price})")
        return True


PAYMENT_METHODS = {
    FreeReencryptions.NAME: FreeReencryptions,
    SubscriptionManagerPayment.NAME: SubscriptionManagerPayment,
}
