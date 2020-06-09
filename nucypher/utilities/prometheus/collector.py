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

try:
    from prometheus_client import Gauge, Enum, Counter, Info, Histogram, Summary
except ImportError:
    raise ImportError('prometheus_client is not installed - Install it and try again.')

from abc import ABC, abstractmethod
from eth_typing.evm import ChecksumAddress

import nucypher
from nucypher.blockchain.eth.actors import NucypherTokenActor
from nucypher.blockchain.eth.agents import ContractAgency, PolicyManagerAgent, StakingEscrowAgent, WorkLockAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry

from prometheus_client.registry import CollectorRegistry, REGISTRY

from typing import Dict, Union

ContractAgents = Union[StakingEscrowAgent, WorkLockAgent, PolicyManagerAgent]


class MetricsCollector(ABC):
    class CollectorError(Exception):
        pass

    class CollectorNotInitialized(Exception):
        """Raised when the Collector was not initialized before being used."""

    @abstractmethod
    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        return NotImplemented

    @abstractmethod
    def collect(self) -> None:
        return NotImplemented


class BaseMetricsCollector(MetricsCollector):
    def __init__(self):
        self.metrics = None

    def collect(self) -> None:
        if not self.metrics:
            raise self.CollectorNotInitialized

        self._collect_internal()

    @abstractmethod
    def _collect_internal(self):
        return NotImplemented


class UrsulaInfoMetricsCollector(BaseMetricsCollector):
    def __init__(self, ursula: 'Ursula'):
        super().__init__()
        self.ursula = ursula

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        self.metrics = {
            "host_info": Info(f'{metrics_prefix}_host_info', 'Description of info', registry=registry),
            "learning_status": Enum(f'{metrics_prefix}_node_discovery', 'Learning loop status',
                                    states=['starting', 'running', 'stopped'], registry=registry),
            "known_nodes_gauge": Gauge(f'{metrics_prefix}_known_nodes',
                                       'Number of currently known nodes',
                                       registry=registry),
            "work_orders_gauge": Gauge(f'{metrics_prefix}_work_orders',
                                       'Number of accepted work orders',
                                       registry=registry),
            "policies_held_gauge": Gauge(f'{metrics_prefix}_policies_held',
                                         'Policies held',
                                         registry=registry),
        }

    def _collect_internal(self) -> None:
        # info
        base_payload = {'app_version': nucypher.__version__,
                        'teacher_version': str(self.ursula.TEACHER_VERSION),
                        'host': str(self.ursula.rest_interface),
                        'domains': str(', '.join(self.ursula.learning_domains)),
                        'fleet_state': str(self.ursula.known_nodes.checksum),
                        'known_nodes': str(len(self.ursula.known_nodes))
                        }

        self.metrics["learning_status"].state('running' if self.ursula._learning_task.running else 'stopped')
        self.metrics["known_nodes_gauge"].set(len(self.ursula.known_nodes))
        self.metrics["work_orders_gauge"].set(len(self.ursula.work_orders()))

        if not self.ursula.federated_only:
            staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.ursula.registry)
            locked = staking_agent.get_locked_tokens(staker_address=self.ursula.checksum_address, periods=1)
            missing_commitments = staking_agent.get_missing_commitments(
                checksum_address=self.ursula.checksum_address)
            decentralized_payload = {'provider': str(self.ursula.provider_uri),
                                     'active_stake': str(locked),
                                     'missing_commitments': str(missing_commitments)}
            base_payload.update(decentralized_payload)

            # TODO should this be here?
            self.metrics["policies_held_gauge"].set(len(self.ursula.datastore.get_all_policy_arrangements()))

        self.metrics["host_info"].info(base_payload)


class BlockchainMetricsCollector(BaseMetricsCollector):
    def __init__(self, provider_uri: str):
        super().__init__()
        self.provider_uri = provider_uri

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        self.metrics = {
            "current_eth_block_number": Gauge(f'{metrics_prefix}_current_eth_block_number',
                                              'Current Ethereum block',
                                              registry=registry),
        }

    def _collect_internal(self) -> None:
        blockchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=self.provider_uri)
        self.metrics["current_eth_block_number"].set(blockchain.client.block_number)


class StakerMetricsCollector(BaseMetricsCollector):
    def __init__(self, staker_address: ChecksumAddress, contract_registry: BaseContractRegistry):
        super().__init__()
        self.staker_address = staker_address
        self.contract_registry = contract_registry

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        self.metrics = {
            "current_period_gauge": Gauge(f'{metrics_prefix}_current_period', 'Current period', registry=registry),
            "eth_balance_gauge": Gauge(f'{metrics_prefix}_staker_eth_balance', 'Ethereum balance', registry=registry),
            "token_balance_gauge": Gauge(f'{metrics_prefix}_staker_token_balance', 'NuNit balance', registry=registry),
            "substakes_count_gauge": Gauge(f'{metrics_prefix}_substakes_count', 'Substakes count', registry=registry),
            "active_stake_gauge": Gauge(f'{metrics_prefix}_active_stake', 'Active stake', registry=registry),
            "unlocked_tokens_gauge": Gauge(f'{metrics_prefix}_unlocked_tokens',
                                           'Amount of unlocked tokens',
                                           registry=registry),
            "owned_tokens_gauge": Gauge(f'{metrics_prefix}_owned_tokens',
                                        'All tokens that belong to the staker, including '
                                        'locked, unlocked and rewards',
                                        registry=registry),
            "missing_commitments_gauge": Gauge(f'{metrics_prefix}_missing_commitments',
                                               'Currently missed commitments',
                                               registry=registry),
        }

    def _collect_internal(self) -> None:
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.contract_registry)

        # current period
        self.metrics["current_period_gauge"].set(staking_agent.get_current_period())

        # balances
        nucypher_token_actor = NucypherTokenActor(self.contract_registry, checksum_address=self.staker_address)
        self.metrics["eth_balance_gauge"].set(nucypher_token_actor.eth_balance)
        self.metrics["token_balance_gauge"].set(int(nucypher_token_actor.token_balance))

        # stake information
        self.metrics["substakes_count_gauge"].set(
            staking_agent.contract.functions.getSubStakesLength(self.staker_address).call())

        locked = staking_agent.get_locked_tokens(staker_address=self.staker_address, periods=1)
        self.metrics["active_stake_gauge"].set(locked)

        owned_tokens = staking_agent.owned_tokens(self.staker_address)
        unlocked_tokens = owned_tokens - locked
        self.metrics["unlocked_tokens_gauge"].set(unlocked_tokens)
        self.metrics["owned_tokens_gauge"].set(owned_tokens)

        # missed commitments
        missing_commitments = staking_agent.get_missing_commitments(checksum_address=self.staker_address)
        self.metrics["missing_commitments_gauge"].set(missing_commitments)


class WorkerMetricsCollector(BaseMetricsCollector):
    def __init__(self, worker_address: ChecksumAddress, contract_registry: BaseContractRegistry):
        super().__init__()
        self.worker_address = worker_address
        self.contract_registry = contract_registry

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        self.metrics = {
            "worker_eth_balance_gauge": Gauge(f'{metrics_prefix}_worker_eth_balance',
                                              'Worker Ethereum balance',
                                              registry=registry),
            "worker_token_balance_gauge": Gauge(f'{metrics_prefix}_worker_token_balance',
                                                'Worker NuNit balance',
                                                registry=registry),
        }

    def _collect_internal(self) -> None:
        nucypher_worker_token_actor = NucypherTokenActor(self.contract_registry, checksum_address=self.worker_address)
        self.metrics["worker_eth_balance_gauge"].set(nucypher_worker_token_actor.eth_balance)
        self.metrics["worker_token_balance_gauge"].set(int(nucypher_worker_token_actor.token_balance))


class WorkLockMetricsCollector(BaseMetricsCollector):
    def __init__(self, staker_address: ChecksumAddress, contract_registry: BaseContractRegistry):
        super().__init__()
        self.staker_address = staker_address
        self.contract_registry = contract_registry

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        self.metrics = {
            "available_refund_gauge": Gauge(f'{metrics_prefix}_available_refund',
                                            'Available refund',
                                            registry=registry),
            "worklock_remaining_work_gauge": Gauge(f'{metrics_prefix}_worklock_refund_remaining_work',
                                                   'Worklock remaining work',
                                                   registry=registry),
            "worklock_refund_completed_work_gauge": Gauge(f'{metrics_prefix}_worklock_refund_completedWork',
                                                          'Worklock completed work',
                                                          registry=registry),
        }

    def _collect_internal(self) -> None:
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.contract_registry)
        worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=self.contract_registry)

        self.metrics["available_refund_gauge"].set(
            worklock_agent.get_available_refund(checksum_address=self.staker_address))

        self.metrics["worklock_remaining_work_gauge"].set(
            worklock_agent.get_remaining_work(checksum_address=self.staker_address)
        )

        self.metrics["worklock_refund_completed_work_gauge"].set(
            staking_agent.get_completed_work(bidder_address=self.staker_address) -
            worklock_agent.get_refunded_work(checksum_address=self.staker_address)
        )


class EventMetricsCollector(BaseMetricsCollector):
    def __init__(self,
                 event_name: str,
                 event_args_config: Dict[str, tuple],
                 argument_filters: Dict[str, str],
                 contract_agent: ContractAgents):
        super().__init__()
        self.event_name = event_name
        self.contract_agent = contract_agent
        self.event_filter = contract_agent.contract.events[event_name].createFilter(fromBlock='latest',
                                                                                    argument_filters=argument_filters)
        self.event_args_config = event_args_config

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        self.metrics = dict()
        for arg_name in self.event_args_config:
            metric_class, metric_name, metric_doc = self.event_args_config[arg_name]
            self.metrics[self._get_arg_metric_key(arg_name)] = metric_class(metric_name, metric_doc, registry=registry)

    def _collect_internal(self) -> None:
        events = self.event_filter.get_new_entries()
        for event in events:
            self._event_occurred(event)

    def _event_occurred(self, event) -> None:
        for arg_name in self.event_args_config:
            if arg_name == "block_number":
                self.metrics[self._get_arg_metric_key("block_number")].set(event["blockNumber"])
                continue
            self.metrics[self._get_arg_metric_key(arg_name)].set(event['args'][arg_name])

    def _get_arg_metric_key(self, arg_name: str):
        return f'{self.event_name}_{arg_name}'


class ReStakeEventMetricsCollector(EventMetricsCollector):
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'ReStakeSet', *args, **kwargs):
        super().__init__(event_name=event_name, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)

        metric_key = self._get_arg_metric_key("reStake")
        self.metrics[metric_key].set(self.contract_agent.is_restaking(self.staker_address))


class WindDownEventMetricsCollector(EventMetricsCollector):
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'WindDownSet', *args, **kwargs):
        super().__init__(event_name=event_name, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)

        metric_key = self._get_arg_metric_key("windDown")
        self.metrics[metric_key].set(self.contract_agent.is_winding_down(self.staker_address))


class WorkerBondedEventMetricsCollector(EventMetricsCollector):
    def __init__(self,
                 staker_address:
                 ChecksumAddress,
                 worker_address: ChecksumAddress,
                 event_name: str = 'WorkerBonded',
                 *args,
                 **kwargs):
        super().__init__(event_name=event_name, *args, **kwargs)
        self.staker_address = staker_address
        self.worker_address = worker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)
        self.metrics["current_worker_is_me_gauge"] = Gauge(f'{metrics_prefix}_current_worker_is_me',
                                                           'Current worker is me',
                                                           registry=registry)

    def _event_occurred(self, event) -> None:
        super()._event_occurred(event)
        self.metrics["current_worker_is_me_gauge"].set(
            self.contract_agent.get_worker_from_staker(self.staker_address) == self.worker_address)


class BidEventMetricsCollector(EventMetricsCollector):
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'Bid', *args, **kwargs):
        super().__init__(event_name=event_name, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)

        if "worklock_deposited_eth_gauge" not in self.metrics:
            # TODO Gross and needs to be linked with RefundEventMetricsCollector somehow
            self.metrics["worklock_deposited_eth_gauge"] = Gauge(f'{metrics_prefix}_worklock_current_deposited_eth',
                                                                 'Worklock deposited ETH',
                                                                 registry=registry)

    def _event_occurred(self, event) -> None:
        super()._event_occurred(event)
        self.metrics["worklock_deposited_eth_gauge"].set(
            self.contract_agent.get_deposited_eth(self.staker_address))


class RefundEventMetricsCollector(EventMetricsCollector):
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'Refund', *args, **kwargs):
        super().__init__(event_name=event_name, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry = REGISTRY) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)
        if "worklock_deposited_eth_gauge" not in self.metrics:
            # TODO Gross and needs to be linked with BidEventMetricsCollector somehow
            self.metrics["worklock_deposited_eth_gauge"] = Gauge(f'{metrics_prefix}_worklock_current_deposited_eth',
                                                                 'Worklock deposited ETH',
                                                                 registry=registry)

    def _event_occurred(self, event) -> None:
        super()._event_occurred(event)
        self.metrics["worklock_deposited_eth_gauge"].set(
            self.contract_agent.get_deposited_eth(self.staker_address))
