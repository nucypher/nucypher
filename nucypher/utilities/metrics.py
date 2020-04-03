try:
    from prometheus_client import Gauge, Enum, Counter, Info
except ImportError:
    raise ImportError('prometheus_client is not installed - Install it and try again.')
from twisted.internet import reactor, task

import nucypher
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, WorkLockAgent, PolicyManagerAgent
from nucypher.blockchain.eth.token import NU
from typing import List


class EventMetricsCollector:

    def __init__(self, contract_agent, event_name, argument_filters, metrics):
        self.event_filter = contract_agent.contract.events[event_name].createFilter(fromBlock='latest',
                                                                                    argument_filters=argument_filters)
        self.metrics = metrics

    def collect(self):
        for event in self.event_filter.get_new_entries():
            for arg in self.metrics.keys():
                if arg == "block_number":
                    self.metrics["block_number"].set(event.block_number)
                    continue
                self.metrics[arg].set(event['args'][arg])


def collect_prometheus_metrics(ursula, event_metrics_collectors: List[EventMetricsCollector], node_metrics):
    base_payload = {'app_version': nucypher.__version__,
                    'teacher_version': str(ursula.TEACHER_VERSION),
                    'host': str(ursula.rest_interface),
                    'domains': str(', '.join(ursula.learning_domains)),
                    'fleet_state': str(ursula.known_nodes.checksum),
                    'known_nodes': str(len(ursula.known_nodes))
                    }

    node_metrics["learning_status"].state('running' if ursula._learning_task.running else 'stopped')
    node_metrics["known_nodes_gauge"].set(len(ursula.known_nodes))
    node_metrics["work_orders_gauge"].set(len(ursula.work_orders()))

    if not ursula.federated_only:
        for event_metrics_collector in event_metrics_collectors:
            event_metrics_collector.collect()

        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)
        work_lock_agent = ContractAgency.get_agent(WorkLockAgent, registry=ursula.registry)

        locked = staking_agent.get_locked_tokens(staker_address=ursula.checksum_address, periods=1)

        node_metrics["active_stake_gauge"].set(locked)


        owned_tokens = staking_agent.owned_tokens(ursula.checksum_address)

        unlocked_tokens = owned_tokens - locked

        node_metrics["unlocked_tokens_gauge"].set(unlocked_tokens)

        node_metrics["owned_tokens_gauge"].set(owned_tokens)

        node_metrics["available_refund"].set(work_lock_agent.get_available_refund(checksum_address=ursula.checksum_address))

        node_metrics["policies_held_gauge"].set(len(ursula.datastore.get_all_policy_arrangements()))

        node_metrics["current_period_gauge"].set(staking_agent.get_current_period())

        missing_confirmations = staking_agent.get_missing_confirmations(
            checksum_address=ursula.checksum_address)  # TODO: lol
        node_metrics["missing_confirmation_gauge"].set(missing_confirmations)

        decentralized_payload = {'provider': str(ursula.provider_uri),
                                 'active_stake': str(locked),
                                 'missing_confirmations': str(missing_confirmations)}

        base_payload.update(decentralized_payload)

    node_metrics["host_info"].info(base_payload)


def get_event_metrics_collectors(ursula, metrics_prefix):
    if ursula.federated_only:
        return {}

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)
    work_lock_agent = ContractAgency.get_agent(WorkLockAgent, registry=ursula.registry)
    policy_manager_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=ursula.registry)

    event_collectors_config = (
        {
            "name": "deposited", "contract_agent": staking_agent, "event": "Deposited",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_deposited_value', 'Deposited value'),
                        "periods": Gauge(f'{metrics_prefix}_deposited_periods', 'Deposited periods'),
                        "block_number": Gauge(f'{metrics_prefix}_deposited_block_number', 'Block number')}
        },
        {
            "name": "locked", "contract_agent": staking_agent, "event": "Locked",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_locked_value', 'Locked valued'),
                        "periods": Gauge(f'{metrics_prefix}_locked_periods', 'Locked periods'),
                        "block_number": Gauge(f'{metrics_prefix}_locked_block_number', 'Block number')}
        },
        {
            "name": "divided", "contract_agent": staking_agent, "event": "Divided",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"newValue": Gauge(f'{metrics_prefix}_divided_new_value', 'New value of divided sub stake'),
                        "periods": Gauge(f'{metrics_prefix}_divided_periods',
                                         'Amount of periods for extending sub stake'),
                        "block_number": Gauge(f'{metrics_prefix}_divided_block_number', 'Block number')}
        },
        {
            "name": "prolonged", "contract_agent": staking_agent, "event": "Prolonged",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_prolonged_value', 'Prolonged value'),
                        "periods": Gauge(f'{metrics_prefix}_prolonged_periods', 'Prolonged periods'),
                        "block_number": Gauge(f'{metrics_prefix}_prolonged_block_number', 'Block number')}
        },
        {
            "name": "withdrawn", "contract_agent": staking_agent, "event": "Withdrawn",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_withdrawn_value', 'Withdrawn value'),
                        "block_number": Gauge(f'{metrics_prefix}_withdrawn_block_number', 'Block number')}
        },
        {
            "name": "activity_confirmed", "contract_agent": staking_agent, "event": "ActivityConfirmed",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_activity_confirmed_value',
                                       'Activity confirmed with value of locked tokens'),
                        "period": Gauge(f'{metrics_prefix}_activity_confirmed_period',
                                        'Activity confirmed period'),
                        "block_number": Gauge(f'{metrics_prefix}_activity_confirmed_block_number', 'Block number')}
        },
        {
            "name": "mined", "contract_agent": staking_agent, "event": "Mined",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_mined_value', 'Mined value'),
                        "period": Gauge(f'{metrics_prefix}_mined_period', 'Mined period'),
                        "block_number": Gauge(f'{metrics_prefix}_mined_block_number', 'Block number')}
        },
        {
            "name": "slashed_reward", "contract_agent": staking_agent, "event": "Slashed",
            "argument_filters": {"investigator": ursula.checksum_address},
            "metrics": {"reward": Gauge(f'{metrics_prefix}_slashed_reward', 'Reward for investigating slasher'),
                        "block_number": Gauge(f'{metrics_prefix}_slashed_reward_block_number', 'Block number')}
        },
        {
            "name": "slashed_penalty", "contract_agent": staking_agent, "event": "Slashed",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"penalty": Gauge(f'{metrics_prefix}_slashed_penalty', 'Penalty for slashing'),
                        "block_number": Gauge(f'{metrics_prefix}_slashed_penalty_block_number', 'Block number')}
        },
        {
            "name": "restake_set", "contract_agent": staking_agent, "event": "ReStakeSet",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"reStake": Gauge(f'{metrics_prefix}_restake_set', 'Restake set'),
                        "block_number": Gauge(f'{metrics_prefix}_restake_set_block_number', 'Block number')}
        },
        {
            "name": "restake_locked", "contract_agent": staking_agent, "event": "ReStakeLocked",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"lockUntilPeriod": Gauge(f'{metrics_prefix}_restake_locked_until_period', 'Restake locked'),
                        "block_number": Gauge(f'{metrics_prefix}_restake_locked_block_number', 'Block number')}
        },
        {
            "name": "wind_down_set", "contract_agent": staking_agent, "event": "WindDownSet",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"windDown": Gauge(f'{metrics_prefix}_wind_down_set_wind_down', 'is windDown'),
                        "block_number": Gauge(f'{metrics_prefix}_wind_down_set_block_number', 'Block number')}
        },
        {
            "name": "worker_set", "contract_agent": staking_agent, "event": "WorkerSet",
            "argument_filters": {"staker": ursula.checksum_address},
            "metrics": {"startPeriod": Gauge(f'{metrics_prefix}_worker_set_start_period', 'New worker was set'),
                        "block_number": Gauge(f'{metrics_prefix}_worker_set_block_number', 'Block number')}
        },
        {
            "name": "work_lock_deposited", "contract_agent": work_lock_agent, "event": "Deposited",
            "argument_filters": {"sender": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_worklock_deposited_value', 'Deposited value'),
                        "block_number": Gauge(f'{metrics_prefix}_worklock_deposited_block_number', 'Block number')}
        },
        {
            "name": "work_lock_bid", "contract_agent": work_lock_agent, "event": "Bid",
            "argument_filters": {"sender": ursula.checksum_address},
            "metrics": {"depositedETH": Gauge(f'{metrics_prefix}_worklock_bid_depositedETH', 'Deposited ETH value'),
                        "block_number": Gauge(f'{metrics_prefix}_worklock_bid_block_number', 'Block number')}
        },
        {
            "name": "work_lock_claimed", "contract_agent": work_lock_agent, "event": "Claimed",
            "argument_filters": {"sender": ursula.checksum_address},
            "metrics": {
                "claimedTokens": Gauge(f'{metrics_prefix}_worklock_claimed_claimedTokens', 'Claimed tokens value'),
            "block_number": Gauge(f'{metrics_prefix}_worklock_claimed_block_number', 'Block number')}
        },
        {
            "name": "work_lock_refund", "contract_agent": work_lock_agent, "event": "Refund",
            "argument_filters": {"sender": ursula.checksum_address},
            "metrics": {
                "refundETH": Gauge(f'{metrics_prefix}_worklock_refund_refundETH', 'Refunded ETH'),
                "completedWork": Gauge(f'{metrics_prefix}_worklock_refund_completedWork', 'Completed work'),
                "block_number": Gauge(f'{metrics_prefix}_worklock_refund_block_number', 'Block number')
            }
        },
        {
            "name": "work_lock_canceled", "contract_agent": work_lock_agent, "event": "Canceled",
            "argument_filters": {"sender": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_worklock_canceled_value', 'Canceled value'),
                        "block_number": Gauge(f'{metrics_prefix}_worklock_canceled_block_number', 'Block number')}
        },
        {
            "name": "policy_withdrawn_reward", "contract_agent": policy_manager_agent, "event": "Withdrawn",
            "argument_filters": {"recipient": ursula.checksum_address},
            "metrics": {"value": Gauge(f'{metrics_prefix}_policy_withdrawn_reward', 'Policy reward'),
                        "block_number": Gauge(f'{metrics_prefix}_policy_withdrawn_reward_block_number', 'Block number')}
        }
    )

    event_metrics_collectors = (EventMetricsCollector(config["contract_agent"], config["event"],
                                config["argument_filters"], config["metrics"]) for config in event_collectors_config)

    return event_metrics_collectors


def initialize_prometheus_exporter(ursula, listen_address, port: int, metrics_prefix) -> None:
    from prometheus_client.twisted import MetricsResource
    from twisted.web.resource import Resource
    from twisted.web.server import Site
    from .json_metrics_export import JSONMetricsResource

    node_metrics = {
        "known_nodes_gauge": Gauge(f'{metrics_prefix}_known_nodes', 'Number of currently known nodes'),
        "work_orders_gauge": Gauge(f'{metrics_prefix}_work_orders', 'Number of accepted work orders'),
        "missing_confirmation_gauge": Gauge(f'{metrics_prefix}_missing_confirmations',
                                            'Currently missed confirmations'),
        "learning_status": Enum(f'{metrics_prefix}_node_discovery', 'Learning loop status',
                                states=['starting', 'running', 'stopped']),
        "eth_balance_gauge": Gauge(f'{metrics_prefix}_eth_balance', 'Ethereum balance'),
        "token_balance_gauge": Gauge(f'{metrics_prefix}_token_balance', 'NuNit balance'),
        "requests_counter": Counter(f'{metrics_prefix}_http_failures', 'HTTP Failures', ['method', 'endpoint']),
        "host_info": Info(f'{metrics_prefix}_host_info', 'Description of info'),
        "active_stake_gauge": Gauge(f'{metrics_prefix}_active_stake', 'Active stake'),
        "owned_tokens_gauge": Gauge(f'{metrics_prefix}_owned_tokens', 'All tokens that belong to the staker, including '
                                                                      'locked, unlocked and rewards'),
        "unlocked_tokens_gauge": Gauge(f'{metrics_prefix}_unlocked_tokens', 'Amount of unlocked tokens'),
        "available_refund_gauge": Gauge(f'{metrics_prefix}_available_refund', 'Available refund'),
        "policies_held_gauge": Gauge(f'{metrics_prefix}_policies_held', 'Policies held'),
        "current_period_gauge": Gauge(f'{metrics_prefix}_current_period', 'Current period')
    }

    event_metrics_collectors = get_event_metrics_collectors(ursula, metrics_prefix)

    # Scheduling
    metrics_task = task.LoopingCall(collect_prometheus_metrics, ursula=ursula,
                                    event_metrics_collectors=event_metrics_collectors, node_metrics=node_metrics)
    metrics_task.start(interval=10, now=False)  # TODO: make configurable

    # WSGI Service
    root = Resource()
    root.putChild(b'metrics', MetricsResource())
    root.putChild(b'json_metrics', JSONMetricsResource())
    factory = Site(root)
    reactor.listenTCP(port, factory, interface=listen_address)
