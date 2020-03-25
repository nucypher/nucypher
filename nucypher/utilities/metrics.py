try:
    from prometheus_client import Gauge, Enum, Counter, Info
except ImportError:
    raise ImportError('prometheus_client is not installed - Install it and try again.')
from twisted.internet import reactor, task

import nucypher
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent

from nucypher.blockchain.eth.actors import NucypherTokenActor

# Metrics
known_nodes_guage = Gauge('known_nodes', 'Number of currently known nodes')
work_orders_guage = Gauge('work_orders', 'Number of accepted work orders')
missing_confirmation_guage = Gauge('missing_confirmations', 'Currently missed confirmations')
learning_status = Enum('node_discovery', 'Learning loop status', states=['starting', 'running', 'stopped'])
eth_balance_gauge = Gauge('eth_balance', 'Ethereum balance')
token_balance_gauge = Gauge('token_balance', 'NuNit balance')
requests_counter = Counter('http_failures', 'HTTP Failures', ['method', 'endpoint'])
host_info = Info('host_info', 'Description of info')
active_stake_gauge = Gauge('active_stake', 'Active stake')

deposited_value_gauge = Gauge('deposited_value', 'Deposited value')
locked_value_gauge = Gauge('locked_value', 'Locked valued')
divided_sub_stake_new_value_gauge = Gauge('divided_sub_stake_new_value', 'New value of divided sbu stake')
prolonged_value_gauge = Gauge('prolonged_value', 'Prolonged value')
withdrawn_value_gauge = Gauge('withdrawn_value', 'Withdrawn value')
activity_confirmed_value_gauge = Gauge('activity_confirmed_value', 'Activity confirmed with value of locked tokens')
mined_value_gauge = Gauge('mined_value', 'Mined value')
reward_for_slashing_gauge = Gauge('reward_for_slashing', 'Reward for investigating slasher')
penalty_for_slashing_gauge = Gauge('penalty_for_slashing', 'Penalty for slashing')


def collect_prometheus_metrics(ursula, filters):
    base_payload = {'app_version': nucypher.__version__,
                    'teacher_version': str(ursula.TEACHER_VERSION),
                    'host': str(ursula.rest_interface),
                    'domains': str(', '.join(ursula.learning_domains)),
                    'fleet_state': str(ursula.known_nodes.checksum),
                    'known_nodes': str(len(ursula.known_nodes))
                    }

    learning_status.state('running' if ursula._learning_task.running else 'stopped')
    known_nodes_guage.set(len(ursula.known_nodes))
    work_orders_guage.set(len(ursula.work_orders()))

    if not ursula.federated_only:

        # nucypher_token_actor = NucypherTokenActor(ursula.registry, checksum_address=ursula.checksum_address)
        # eth_balance_gauge.set(nucypher_token_actor.eth_balance)
        # token_balance_gauge.set(nucypher_token_actor.token_balance)

        for event in filters["deposited_value_filter"].get_new_entries():
            deposited_value_gauge.set(event['args']['value'])

        for event in filters["locked_value_filter"].get_new_entries():
            locked_value_gauge.set(event['args']['value'])

        for event in filters["divided_sub_stake_new_value_filter"].get_new_entries():
            divided_sub_stake_new_value_gauge.set(event['args']['new_value'])

        for event in filters["prolonged_value_filter"].get_new_entries():
            prolonged_value_gauge.set(event['args']['value'])

        for event in filters["withdrawn_value_filter"].get_new_entries():
            withdrawn_value_gauge.set(event['args']['value'])

        for event in filters["activity_confirmed_value_filter"].get_new_entries():
            activity_confirmed_value_gauge.set(event['args']['value'])

        for event in filters["mined_value_filter"].get_new_entries():
            mined_value_gauge.set(event['args']['value'])

        for event in filters["reward_for_slashing_value_filter"].get_new_entries():
            reward_for_slashing_gauge.set(event['args']['reward'])

        for event in filters["penalty_for_slashing_filter"].get_new_entries():
            penalty_for_slashing_gauge.set(event['args']['penalty'])

        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)
        locked = staking_agent.get_locked_tokens(staker_address=ursula.checksum_address, periods=1)
        active_stake_gauge.set(locked)

        missing_confirmations = staking_agent.get_missing_confirmations(staker_address=ursula.checksum_address)  # TODO: lol
        missing_confirmation_guage.set(missing_confirmations)

        decentralized_payload = {'provider': str(ursula.provider_uri),
                                 'active_stake': str(locked),
                                 'missing_confirmations': str(missing_confirmations)}

        base_payload.update(decentralized_payload)

    host_info.info(base_payload)


def initialize_prometheus_exporter(ursula, port: int) -> None:
    from prometheus_client.twisted import MetricsResource
    from twisted.web.resource import Resource
    from twisted.web.server import Site

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)
    deposited_value_filter = staking_agent.contract.events.Deposited.createFilter(fromBlock='latest',
                                                                             argument_filters={
                                                                                 'staker': ursula.checksum_address})
    locked_value_filter = staking_agent.contract.events.Locked.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})
    divided_sub_stake_new_value_filter = staking_agent.contract.events.Divided.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})
    prolonged_value_filter = staking_agent.contract.events.Prolonged.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})
    withdrawn_value_filter = staking_agent.contract.events.Withdrawn.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})
    activity_confirmed_value_filter = staking_agent.contract.events.ActivityConfirmed.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})
    mined_value_filter = staking_agent.contract.events.Mined.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})
    reward_for_slashing_value_filter = staking_agent.contract.events.Slashed.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'investigator': ursula.checksum_address})
    penalty_for_slashing_filter = staking_agent.contract.events.Deposited.createFilter(fromBlock='latest',
                                                                                  argument_filters={
                                                                                      'staker': ursula.checksum_address})

    filters = {"deposited_value_filter": deposited_value_filter,
               "locked_value_filter": locked_value_filter,
               "divided_sub_stake_new_value_filter": divided_sub_stake_new_value_filter,
               "prolonged_value_filter": prolonged_value_filter,
               "withdrawn_value_filter": withdrawn_value_filter,
               "activity_confirmed_value_filter": activity_confirmed_value_filter,
               "mined_value_filter": mined_value_filter,
               "reward_for_slashing_value_filter": reward_for_slashing_value_filter,
               "penalty_for_slashing_filter": penalty_for_slashing_filter}

    # Scheduling
    metrics_task = task.LoopingCall(collect_prometheus_metrics, ursula=ursula, filters=filters)
    metrics_task.start(interval=10, now=False)  # TODO: make configurable

    # WSGI Service
    root = Resource()
    root.putChild(b'metrics', MetricsResource())
    factory = Site(root)
    reactor.listenTCP(port, factory)

