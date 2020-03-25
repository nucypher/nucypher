try:
        from prometheus_client import Gauge, Enum, Counter, Info
except ImportError:
    raise ImportError('prometheus_client is not installed - Install it and try again.')
from twisted.internet import reactor, task

import nucypher
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent

from nucypher.blockchain.eth.actors import NucypherTokenActor


def collect_prometheus_metrics(ursula, filters, event_metrics, node_metrics):
    base_payload = {'app_version': nucypher.__version__,
                    'teacher_version': str(ursula.TEACHER_VERSION),
                    'host': str(ursula.rest_interface),
                    'domains': str(', '.join(ursula.learning_domains)),
                    'fleet_state': str(ursula.known_nodes.checksum),
                    'known_nodes': str(len(ursula.known_nodes))
                    }

    node_metrics["learning_status"].state('running' if ursula._learning_task.running else 'stopped')
    node_metrics["known_nodes_guage"].set(len(ursula.known_nodes))
    node_metrics["work_orders_guage"].set(len(ursula.work_orders()))

    if not ursula.federated_only:

        nucypher_token_actor = NucypherTokenActor(ursula.registry, checksum_address=ursula.checksum_address)
        node_metrics["eth_balance_gauge"].set(nucypher_token_actor.eth_balance)
        node_metrics["token_balance_gauge"].set(nucypher_token_actor.token_balance)

        for metric_key, metric_value in event_metrics.items():
            for event in filters[metric_key].get_new_entries():
                for arg in metric_value.keys():
                    metric_value[arg].set(event['args'][arg])

        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)
        locked = staking_agent.get_locked_tokens(staker_address=ursula.checksum_address, periods=1)
        node_metrics["active_stake_gauge"].set(locked)

        missing_confirmations = staking_agent.get_missing_confirmations(
            checksum_address=ursula.checksum_address)  # TODO: lol
        node_metrics["missing_confirmation_guage"].set(missing_confirmations)

        decentralized_payload = {'provider': str(ursula.provider_uri),
                                 'active_stake': str(locked),
                                 'missing_confirmations': str(missing_confirmations)}

        base_payload.update(decentralized_payload)

    node_metrics["host_info"].info(base_payload)


def get_filters(ursula):
    if ursula.federated_only:
        return {}
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)

    # {event_name: filter}
    filters = {
        "deposited": staking_agent.contract.events.Deposited.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address}),
        "locked": staking_agent.contract.events.Locked.createFilter(fromBlock='latest',
                                                                            argument_filters={
                                                                                'staker': ursula.checksum_address}),
        "divided": staking_agent.contract.events.Divided.createFilter(fromBlock='latest',
                                                                                            argument_filters={
                                                                                                'staker': ursula.checksum_address}),
        "prolonged": staking_agent.contract.events.Prolonged.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address}),
        "withdrawn": staking_agent.contract.events.Withdrawn.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address}),
        "activity_confirmed": staking_agent.contract.events.ActivityConfirmed.createFilter(fromBlock='latest',
                                                                                                   argument_filters={
                                                                                                       'staker': ursula.checksum_address}),
        "mined": staking_agent.contract.events.Mined.createFilter(fromBlock='latest',
                                                                          argument_filters={
                                                                              'staker': ursula.checksum_address}),
        "slashed_reward": staking_agent.contract.events.Slashed.createFilter(fromBlock='latest',
                                                                                          argument_filters={
                                                                                              'investigator': ursula.checksum_address}),
        "slashed_penalty": staking_agent.contract.events.Deposited.createFilter(fromBlock='latest',
                                                                                       argument_filters={
                                                                                           'staker': ursula.checksum_address}),
        "restake_set": staking_agent.contract.events.ReStakeSet.createFilter(fromBlock='latest',
                                                                                     argument_filters={
                                                                                         'staker': ursula.checksum_address}),
        "restake_locked": staking_agent.contract.events.ReStakeLocked.createFilter(fromBlock='latest',
                                                                                                  argument_filters={
                                                                                                      'staker': ursula.checksum_address}),
        "work_measurement_set": staking_agent.contract.events.WorkMeasurementSet.createFilter(
                                                                                    fromBlock='latest',
                                                                                    argument_filters={
                                                                                        'staker': ursula.checksum_address}),
        "wind_down_set": staking_agent.contract.events.WindDownSet.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})}
    return filters


def initialize_prometheus_exporter(ursula, host, port: int, metrics_prefix) -> None:
    from prometheus_client.twisted import MetricsResource
    from twisted.web.resource import Resource
    from twisted.web.server import Site

    node_metrics = {
        "known_nodes_guage": Gauge(metrics_prefix + '_known_nodes', 'Number of currently known nodes'),
        "work_orders_guage": Gauge(metrics_prefix + '_work_orders', 'Number of accepted work orders'),
        "missing_confirmation_guage": Gauge(metrics_prefix + '_missing_confirmations', 'Currently missed confirmations'),
        "learning_status": Enum(metrics_prefix + '_node_discovery', 'Learning loop status', states=['starting', 'running', 'stopped']),
        "eth_balance_gauge": Gauge(metrics_prefix + '_eth_balance', 'Ethereum balance'),
        "token_balance_gauge": Gauge(metrics_prefix + '_token_balance', 'NuNit balance'),
        "requests_counter": Counter(metrics_prefix + '_http_failures', 'HTTP Failures', ['method', 'endpoint']),
        "host_info": Info(metrics_prefix + '_host_info', 'Description of info'),
        "active_stake_gauge": Gauge(metrics_prefix + '_active_stake', 'Active stake')
    }

    # {event_name: {event.argument: metric}}
    event_metrics = {
        "deposited": {"value": Gauge(metrics_prefix + '_deposited_value', 'Deposited value'),
                      "periods": Gauge(metrics_prefix + '_deposited_periods', 'Deposited periods')},
        "locked": {"value":Gauge(metrics_prefix + '_locked_value', 'Locked valued'),
                   "periods":Gauge(metrics_prefix + '_locked_periods', 'Locked periods')},
        "divided": {"newValue": Gauge(metrics_prefix + '_divided_new_value', 'New value of divided sub stake'),
                    "periods": Gauge(metrics_prefix + '_divided_periods', 'Amount of periods for extending sub stake')},
        "prolonged": {"value": Gauge(metrics_prefix + '_prolonged_value', 'Prolonged value'),
                      "periods": Gauge(metrics_prefix + '_prolonged_periods', 'Prolonged periods')},
        "withdrawn": {"value": Gauge(metrics_prefix + '_withdrawn_value', 'Withdrawn value')},
        "activity_confirmed": {"value": Gauge(metrics_prefix + '_activity_confirmed_value', 'Activity confirmed with value of locked tokens'),
                               "period": Gauge(metrics_prefix + '_activity_confirmed_period', 'Activity confirmed period')},
        "mined": {"value": Gauge(metrics_prefix + '_mined_value', 'Mined value'),
                  "period": Gauge(metrics_prefix + '_mined_period', 'Mined period')},
        "slashed_reward": {"reward": Gauge(metrics_prefix + '_slashed_reward', 'Reward for investigating slasher')},
        "slashed_penalty": {"penalty": Gauge(metrics_prefix + '_slashed_penalty', 'Penalty for slashing')},
        "restake_set": {"reStake": Gauge(metrics_prefix + '_restake_set', '')},
        "restake_locked": {"lockUntilPeriod": Gauge(metrics_prefix + '_restake_locked_until_period', '')},
        "work_measurement_set": {"measureWork": Gauge(metrics_prefix + '_work_measurement_set_measure_work', '')},
        "wind_down_set": {"windDown": Gauge(metrics_prefix + '_wind_down_set_wind_down', 'is windDown')}
    }

    # Scheduling
    metrics_task = task.LoopingCall(collect_prometheus_metrics, ursula=ursula, filters=get_filters(ursula),
                                    event_metrics=event_metrics, node_metrics=node_metrics)
    metrics_task.start(interval=10, now=False)  # TODO: make configurable

    # WSGI Service
    root = Resource()
    root.putChild(b'metrics', MetricsResource())
    factory = Site(root)
    reactor.listenTCP(port, factory, interface=host)
