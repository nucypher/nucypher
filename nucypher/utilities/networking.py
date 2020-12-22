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


from ipaddress import ip_address

import random
import requests
from requests.exceptions import RequestException, HTTPError
from typing import Union

from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry
from nucypher.acumen.perception import FleetSensor
from nucypher.characters.lawful import Ursula
from nucypher.network.middleware import RestMiddleware, NucypherMiddlewareClient
from nucypher.utilities.logging import Logger


class UnknownIPAddress(RuntimeError):
    pass


RequestErrors = (
    # https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions
    ConnectionError,
    TimeoutError,
    RequestException,
    HTTPError
)

IP_DETECTION_LOGGER = Logger('external-ip-detection')


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
    if not registry:
        # Registry is needed to perform on-chain staking verification.
        registry = InMemoryContractRegistry.from_latest_publication(network=network)
    teacher = Ursula.from_teacher_uri(teacher_uri=top_teacher_url,
                                      registry=registry,
                                      federated_only=federated_only,
                                      min_stake=0)  # TODO: Handle customized min stake here.
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
        log.info(f'Fetched external IP address from default teacher ({top_teacher_url} reported {ip}).')
        return ip


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
            log.info(f'Fetched external IP address from randomly selected known node(s).')
    return ip


def get_external_ip_from_centralized_source(log: Logger = IP_DETECTION_LOGGER) -> Union[str, None]:
    """Use hardcoded URL to determine the external IP address of this host."""
    endpoint = 'https://ifconfig.me/'
    ip = __request(url=endpoint)
    if ip:
        log.info(f'Fetched external IP address from centralized source ({endpoint}).')
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
