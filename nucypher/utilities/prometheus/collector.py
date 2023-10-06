


from nucypher.blockchain.eth.events import ContractEventsThrottler

try:
    from prometheus_client import Enum, Gauge, Info
    from prometheus_client.registry import CollectorRegistry
except ImportError:
    raise ImportError('"prometheus_client" must be installed - run "pip install nucypher[ursula]" and try again.')

from abc import ABC, abstractmethod
from typing import Dict, Type

from eth_typing.evm import ChecksumAddress

import nucypher
from nucypher.blockchain.eth import actors
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    EthereumContractAgent,
    TACoApplicationAgent,
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
    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
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

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "host_info": Info(
                f"{metrics_prefix}_host", "Ursula info", registry=registry
            ),
            "learning_status": Enum(
                f"{metrics_prefix}_node_discovery",
                "Learning loop status",
                states=["starting", "running", "stopped"],
                registry=registry,
            ),
            "known_nodes_gauge": Gauge(
                f"{metrics_prefix}_known_nodes",
                "Number of currently known nodes",
                registry=registry,
            ),
            "reencryption_requests_gauge": Gauge(
                f"{metrics_prefix}_reencryption_requests",
                "Number of accepted work orders",
                registry=registry,
            ),
        }

    def _collect_internal(self) -> None:
        # info
        payload = {
            "app_version": nucypher.__version__,
            "host": str(self.ursula.rest_interface),
            "domain": self.ursula.domain,
            "nickname": str(self.ursula.nickname),
            "nickname_icon": self.ursula.nickname.icon,
            "staking_provider_address": self.ursula.checksum_address,
            "operator_address": self.ursula.operator_address,
        }

        self.metrics["learning_status"].state('running' if self.ursula._learning_task.running else 'stopped')
        self.metrics["known_nodes_gauge"].set(len(self.ursula.known_nodes))
        self.metrics["host_info"].info(payload)


class BlockchainMetricsCollector(BaseMetricsCollector):
    """Collector for Blockchain specific metrics."""

    def __init__(self, eth_endpoint: str):
        super().__init__()
        self.eth_endpoint = eth_endpoint

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "eth_chain_id": Gauge(
                f"{metrics_prefix}_eth_chain_id", "Ethereum Chain ID", registry=registry
            ),
            "eth_current_block_number": Gauge(
                f"{metrics_prefix}_eth_block_number",
                "Current Ethereum block",
                registry=registry,
            ),
        }

    def _collect_internal(self) -> None:
        blockchain = BlockchainInterfaceFactory.get_or_create_interface(
            endpoint=self.eth_endpoint
        )
        self.metrics["eth_chain_id"].set(blockchain.client.chain_id)
        self.metrics["eth_current_block_number"].set(blockchain.client.block_number)


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

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "active_stake_gauge": Gauge(
                f"{metrics_prefix}_associated_active_stake",
                "Total amount of T staked (adapted NU/KEEP and liquid T)",
                registry=registry,
            ),
            "operator_confirmed_gauge": Gauge(
                f"{metrics_prefix}_operator_confirmed",
                "Operator already confirmed",
                registry=registry,
            ),
            "operator_start_gauge": Gauge(
                f"{metrics_prefix}_operator_start_timestamp",
                "Operator start timestamp",
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
        self.metrics["active_stake_gauge"].set(int(authorized))

        staking_provider_info = application_agent.get_staking_provider_info(
            staking_provider=self.staking_provider_address
        )
        self.metrics["operator_confirmed_gauge"].set(
            staking_provider_info.operator_confirmed
        )
        self.metrics["operator_start_gauge"].set(
            staking_provider_info.operator_start_timestamp
        )


class OperatorMetricsCollector(BaseMetricsCollector):
    """Collector for Operator specific metrics."""

    def __init__(
        self,
        domain: str,
        operator_address: ChecksumAddress,
        contract_registry: ContractRegistry,
    ):
        super().__init__()
        self.domain = domain
        self.operator_address = operator_address
        self.contract_registry = contract_registry

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "operator_eth_balance_gauge": Gauge(
                f"{metrics_prefix}_operator_eth_balance",
                "Operator Ethereum balance",
                registry=registry,
            ),
        }

    def _collect_internal(self) -> None:
        operator_token_actor = actors.NucypherTokenActor(
            registry=self.contract_registry,
            domain=self.domain,
            checksum_address=self.operator_address,
        )
        self.metrics["operator_eth_balance_gauge"].set(
            float(operator_token_actor.eth_balance)
        )


class EventMetricsCollector(BaseMetricsCollector):
    """General collector for emitted events."""

    def __init__(
        self,
        event_name: str,
        event_args_config: Dict[str, tuple],
        argument_filters: Dict[str, str],
        contract_agent_class: Type[EthereumContractAgent],
        contract_registry: ContractRegistry,
    ):
        super().__init__()
        self.event_name = event_name
        self.contract_agent_class = contract_agent_class
        self.contract_registry = contract_registry

        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        # this way we don't have to deal with 'latest' at all
        self.filter_current_from_block = contract_agent.blockchain.client.block_number
        self.filter_arguments = argument_filters
        self.event_args_config = event_args_config

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = dict()
        for arg_name in self.event_args_config:
            metric_class, metric_name, metric_doc = self.event_args_config[arg_name]
            metric_key = self._get_arg_metric_key(arg_name)
            self.metrics[metric_key] = metric_class(metric_name, metric_doc, registry=registry)

    def _collect_internal(self) -> None:
        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        from_block = self.filter_current_from_block
        to_block = contract_agent.blockchain.client.block_number
        if from_block >= to_block:
            # we've already checked the latest block and waiting for a new block
            # nothing to see here
            return

        # update last block checked for the next round - from/to block range is inclusive
        # increment before potentially long running execution to improve concurrency handling
        self.filter_current_from_block = to_block + 1

        events_throttler = ContractEventsThrottler(agent=contract_agent,
                                                   event_name=self.event_name,
                                                   from_block=from_block,
                                                   to_block=to_block,
                                                   **self.filter_arguments)
        for event_record in events_throttler:
            self._event_occurred(event_record.raw_event)

    def _event_occurred(self, event) -> None:
        for arg_name in self.event_args_config:
            metric_key = self._get_arg_metric_key(arg_name)
            if arg_name == "block_number":
                self.metrics[metric_key].set(event["blockNumber"])
                continue
            self.metrics[metric_key].set(event['args'][arg_name])

    def _get_arg_metric_key(self, arg_name: str):
        return f'{self.event_name}_{arg_name}'
