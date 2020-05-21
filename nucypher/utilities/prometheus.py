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
    from prometheus_client import Gauge, Enum, Counter, Info
except ImportError:
    raise ImportError('prometheus_client is not installed - Install it and try again.')
from twisted.internet import reactor, task

import nucypher
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent

# Metrics
known_nodes_guage = Gauge('known_nodes', 'Number of currently known nodes')
work_orders_guage = Gauge('work_orders', 'Number of accepted work orders')
missing_commitments_guage = Gauge('missing_commitments', 'Currently missed commitments')
learning_status = Enum('node_discovery', 'Learning loop status', states=['starting', 'running', 'stopped'])
requests_counter = Counter('http_failures', 'HTTP Failures', ['method', 'endpoint'])
host_info = Info('host_info', 'Description of info')
active_stake_gauge = Gauge('active_stake', 'Active stake')


def collect_prometheus_metrics(ursula):
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

        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)
        locked = staking_agent.get_locked_tokens(staker_address=ursula.checksum_address, periods=1)
        active_stake_gauge.set(locked)

        missing_commitments = staking_agent.get_missing_commitments(staker_address=ursula.checksum_address)  # TODO: lol
        missing_commitments_guage.set(missing_commitments)

        decentralized_payload = {'provider': str(ursula.provider_uri),
                                 'active_stake': str(locked),
                                 'missing_commitments': str(missing_commitments)}

        base_payload.update(decentralized_payload)

    host_info.info(base_payload)


def initialize_prometheus_exporter(ursula, port: int) -> None:
    from prometheus_client.twisted import MetricsResource
    from twisted.web.resource import Resource
    from twisted.web.server import Site
    from nucypher.utilities.metrics import collect_prometheus_metrics

    # Scheduling
    metrics_task = task.LoopingCall(collect_prometheus_metrics, ursula=ursula)
    metrics_task.start(interval=10, now=False)  # TODO: make configurable

    # WSGI Service
    root = Resource()
    root.putChild(b'metrics', MetricsResource())
    factory = Site(root)
    reactor.listenTCP(port, factory)
