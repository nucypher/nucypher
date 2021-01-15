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


import random
import requests
from ipaddress import ip_address
from requests.exceptions import RequestException, HTTPError
from typing import Union

from nucypher.config.storages import LocalFileBasedNodeStorage
from nucypher.acumen.perception import FleetSensor
from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry
from nucypher.network.middleware import RestMiddleware, NucypherMiddlewareClient
from nucypher.utilities.logging import Logger


class UnknownIPAddress(RuntimeError):
    pass


class InvalidWorkerIP(RuntimeError):
    """Raised when an Ursula is using an invalid IP address for it's server."""


RequestErrors = (
    # https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions
    ConnectionError,
    TimeoutError,
    RequestException,
    HTTPError
)

RESERVED_IP_ADDRESSES = (
    '0.0.0.0',
    '127.0.0.1',
    '1.2.3.4'
)

IP_DETECTION_LOGGER = Logger('external-ip-detection')



def validate_worker_ip(worker_ip: str) -> None:
    if worker_ip in RESERVED_IP_ADDRESSES:
        raise InvalidWorkerIP(f'{worker_ip} is not a valid or permitted worker IP address.  '
                              f'Verify the rest_host is set to the external IPV4 address')


def __request(url: str, certificate=None) -> Union[str, None]:
    """
    Utility function to send a GET request to a URL returning it's
    text content or None, suppressing all errors. Certificate is
    needed if the remote URL source is self-signed.
    """
    try:
        # 'None' or 'True' will verify self-signed certificates
        response = requests.get(url, verify=certificate)
    except RequestErrors:
        return None
    if response.status_code == 200:
        return response.text


def get_external_ip_from_default_teacher(network: str,
                                         federated_only: bool = False,
                                         log: Logger = IP_DETECTION_LOGGER,
                                         registry: BaseContractRegistry = None
                                         ) -> Union[str, None]:
    from nucypher.characters.lawful import Ursula

    if federated_only and registry:
        raise ValueError('Federated mode must not be true if registry is provided.')
    base_error = 'Cannot determine IP using default teacher'
    try:
        top_teacher_url = RestMiddleware.TEACHER_NODES[network][0]
    except IndexError:
        log.debug(f'{base_error}: No teacher available for network "{network}".')
        return
    except KeyError:
        log.debug(f'{base_error}: Unknown network "{network}".')
        return

    ####
    # TODO: Clean this mess #1481
    node_storage = LocalFileBasedNodeStorage(federated_only=federated_only)
    Ursula.set_cert_storage_function(node_storage.store_node_certificate)
    Ursula.set_federated_mode(federated_only)
    #####

    teacher = Ursula.from_teacher_uri(teacher_uri=top_teacher_url,
                                      federated_only=federated_only,
                                      min_stake=0)  # TODO: Handle customized min stake here.

    # TODO: Pass registry here to verify stake (not essential here since it's a hardcoded node)
    client = NucypherMiddlewareClient()
    try:
        response = client.get(node_or_sprout=teacher, path=f"ping", timeout=2)  # TLS certificate logic within
    except RestMiddleware.UnexpectedResponse:
        # 404, 405, 500, All server response codes handled by will be caught here.
        return  # Default teacher does not support this request - just move on.
    if response.status_code == 200:
        try:
            ip = str(ip_address(response.text))
        except ValueError:
            error = f'Default teacher at {top_teacher_url} returned an invalid IP response; Got {response.text}'
            raise UnknownIPAddress(error)
        log.info(f'Fetched external IP address ({ip}) from default teacher ({top_teacher_url}).')
        return ip
    else:
        log.debug(f'Failed to get external IP from teacher node ({response.status_code})')


def get_external_ip_from_known_nodes(known_nodes: FleetSensor,
                                     sample_size: int = 3,
                                     log: Logger = IP_DETECTION_LOGGER
                                     ) -> Union[str, None]:
    """
    Randomly select a sample of peers to determine the external IP address
    of this host. The first node to reply successfully will be used.
    # TODO: Parallelize the requests and compare results.
    """
    ip = None
    sample = random.sample(known_nodes, sample_size)
    for node in sample:
        ip = __request(url=node.rest_url())
        if ip:
            log.info(f'Fetched external IP address ({ip}) from randomly selected known node(s).')
            return ip


def get_external_ip_from_centralized_source(log: Logger = IP_DETECTION_LOGGER) -> Union[str, None]:
    """Use hardcoded URL to determine the external IP address of this host."""
    endpoint = 'https://ifconfig.me/'
    ip = __request(url=endpoint)
    if ip:
        log.info(f'Fetched external IP address ({ip}) from centralized source ({endpoint}).')
    return ip


def determine_external_ip_address(network: str, known_nodes: FleetSensor = None) -> str:
    """
    Attempts to automatically determine the external IP in the following priority:
    1. Randomly Selected Known Nodes
    2. The Default Teacher URI from RestMiddleware
    3. A centralized IP address service

    If the IP address cannot be determined for any reason UnknownIPAddress is raised.
    """
    rest_host = None

    # primary source
    if known_nodes:
        rest_host = get_external_ip_from_known_nodes(known_nodes=known_nodes)

    # fallback 1
    if not rest_host:
        rest_host = get_external_ip_from_default_teacher(network=network)

    # fallback 2
    if not rest_host:
        rest_host = get_external_ip_from_centralized_source()

    # complete failure!
    if not rest_host:
        raise UnknownIPAddress('External IP address detection failed')
    return rest_host
