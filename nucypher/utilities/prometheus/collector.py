from abc import ABC, abstractmethod
from typing import Dict

from eth_typing.evm import ChecksumAddress
from prometheus_client import Gauge, Info
from prometheus_client.registry import CollectorRegistry
from web3 import Web3

import nucypher
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters import lawful


class MetricsCollector(ABC):
    """Metrics Collector Interface."""

    class CollectorError(Exception):
        pass

    class CollectorNotInitialized(Exception):
        """Raised when the Collector was not initialized before being used."""

    @abstractmethod
    def initialize(self, registry: CollectorRegistry) -> None:
        """Initialize metrics collector."""
        return NotImplemented

    @abstractmethod
    def collect(self) -> None:
        """Collect relevant metrics."""
        return NotImplemented


class BaseMetricsCollector(MetricsCollector):
    """
    Base metrics collector that checks whether collector was initialized before used.

    Subclasses should initialize the self.metrics member in their initialize() method since the
    self.metrics member is used to determine whether initialize was called, and if not an exception is raised.
    """

    def __init__(self):
        self.metrics: Dict = None

    def collect(self) -> None:
        if self.metrics is None:
            raise self.CollectorNotInitialized

        self._collect_internal()

    @abstractmethod
    def _collect_internal(self):
        """
        Called by collect() - subclasses should override this method instead of collect() to ensure that the
        initialization check is always performed.
        """
        # created so that the initialization check does not have to be specified by all subclasses of
        # BaseMetricsCollector; instead it is performed automatically by collect()
        return NotImplemented


class UrsulaInfoMetricsCollector(BaseMetricsCollector):
    """Collector for Ursula specific metrics."""

    def __init__(self, ursula: "lawful.Ursula"):
        super().__init__()
        self.ursula = ursula

    def initialize(self, registry: CollectorRegistry) -> None:
        self.metrics = {
            "client_info": Info("client", "TACo node client info", registry=registry),
            "node_discovery_running": Gauge(
                "node_discovery_running",
                "Node discovery loop status",
                registry=registry,
            ),
            "known_nodes": Gauge(
                "known_nodes",
                "Number of currently known nodes",
                registry=registry,
            ),
        }

    def _collect_internal(self) -> None:
        # info
        payload = {
            "app": "TACo",
            "version": nucypher.__version__,
            "host": str(self.ursula.rest_interface),
            "domain": str(self.ursula.domain),
            "nickname": str(self.ursula.nickname),
            "nickname_icon": self.ursula.nickname.icon,
            "staking_provider_address": self.ursula.checksum_address,
            "operator_address": self.ursula.operator_address,
        }

        self.metrics["client_info"].info(payload)
        self.metrics["node_discovery_running"].set(self.ursula._learning_task.running)
        self.metrics["known_nodes"].set(len(self.ursula.known_nodes))


class BlockchainMetricsCollector(BaseMetricsCollector):
    """Collector for Blockchain specific metrics."""

    def __init__(self, root_net_endpoint: str, child_net_endpoint: str):
        super().__init__()
        self.root_net_endpoint = root_net_endpoint
        self.child_net_endpoint = child_net_endpoint

    def initialize(self, registry: CollectorRegistry) -> None:
        self.metrics = {
            "root_net_chain_id": Gauge(
                "root_net_chain_id", "Root network Chain ID", registry=registry
            ),
            "root_net_current_block_number": Gauge(
                "root_net_current_block_number",
                "Root network current block",
                registry=registry,
            ),
            "child_net_chain_id": Gauge(
                "child_net_chain_id", "Child network Chain ID", registry=registry
            ),
            "child_net_current_block_number": Gauge(
                "child_net_current_block_number",
                "Child network current block",
                registry=registry,
            ),
        }

    def _collect_internal(self) -> None:
        root_blockchain = BlockchainInterfaceFactory.get_or_create_interface(
            endpoint=self.root_net_endpoint
        )
        child_blockchain = BlockchainInterfaceFactory.get_or_create_interface(
            endpoint=self.child_net_endpoint
        )
        self.metrics["root_net_chain_id"].set(root_blockchain.client.chain_id)
        self.metrics["root_net_current_block_number"].set(
            root_blockchain.client.block_number
        )
        self.metrics["child_net_chain_id"].set(child_blockchain.client.chain_id)
        self.metrics["child_net_current_block_number"].set(
            child_blockchain.client.block_number
        )


class StakingProviderMetricsCollector(BaseMetricsCollector):
    """Collector for Staking Provider associated metrics."""

    def __init__(
        self,
        staking_provider_address: ChecksumAddress,
        contract_registry: ContractRegistry,
        eth_endpoint: str,
    ):
        super().__init__()
        self.staking_provider_address = staking_provider_address
        self.contract_registry = contract_registry
        self.eth_endpoint = eth_endpoint

    def initialize(self, registry: CollectorRegistry) -> None:
        self.metrics = {
            "active_stake": Gauge(
                "active_stake",
                "Total amount of T staked",
                registry=registry,
            ),
            "operator_bonded_timestamp": Gauge(
                "operator_bonded_timestamp",
                "Timestamp operator bonded to stake",
                registry=registry,
            ),
        }

    def _collect_internal(self) -> None:
        application_agent = ContractAgency.get_agent(
            TACoApplicationAgent,
            registry=self.contract_registry,
            blockchain_endpoint=self.eth_endpoint,
        )
        authorized = application_agent.get_authorized_stake(
            staking_provider=self.staking_provider_address
        )
        self.metrics["active_stake"].set(Web3.from_wei(authorized, "ether"))

        staking_provider_info = application_agent.get_staking_provider_info(
            staking_provider=self.staking_provider_address
        )
        self.metrics["operator_bonded_timestamp"].set(
            staking_provider_info.operator_start_timestamp
        )


class OperatorMetricsCollector(BaseMetricsCollector):
    """Collector for Operator specific metrics."""

    def __init__(
        self,
        operator_address: ChecksumAddress,
        contract_registry: ContractRegistry,
        polygon_endpoint: str,
    ):
        super().__init__()
        self.operator_address = operator_address
        self.contract_registry = contract_registry
        self.polygon_endpoint = polygon_endpoint

    def initialize(self, registry: CollectorRegistry) -> None:
        self.metrics = {
            "operator_confirmed": Gauge(
                "operator_confirmed",
                "Operator already confirmed",
                registry=registry,
            ),
            "operator_matic_balance": Gauge(
                "operator_matic_balance", "Operator MATIC balance", registry=registry
            ),
        }

    def _collect_internal(self) -> None:
        child_application_agent = ContractAgency.get_agent(
            TACoChildApplicationAgent,
            registry=self.contract_registry,
            blockchain_endpoint=self.polygon_endpoint,
        )
        self.metrics["operator_confirmed"].set(
            child_application_agent.is_operator_confirmed(
                operator_address=self.operator_address
            )
        )
        matic_balance = child_application_agent.blockchain.client.get_balance(
            self.operator_address
        )
        self.metrics["operator_matic_balance"].set(
            Web3.from_wei(matic_balance, "ether")
        )
