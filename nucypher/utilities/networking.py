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
from requests.exceptions import RequestException, HTTPError
from typing import Union

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


def get_external_ip_from_url_source(url: str, certificate=None) -> Union[str, None]:
    """Certificate is needed if the remote URL source is self-signed."""
    try:
        # 'None' or 'True' will verify self-signed certificates
        response = requests.get(url, verify=certificate)
    except RequestErrors:
        return None
    if response.status_code == 200:
        return response.text


def get_external_ip_from_default_teacher(network: str,
                                         federated_only: bool = False,
                                         log=None
                                         ) -> Union[str, None]:
    if not log:
        log = Logger('whoami')

    try:
        top_teacher_url = RestMiddleware.TEACHER_NODES[network][0]
    except (KeyError, IndexError):
        # unknown network or no default teachers available
        return  # just move on.
    teacher = Ursula.from_teacher_uri(teacher_uri=top_teacher_url,
                                      federated_only=federated_only,
                                      min_stake=0)  # TODO: Handle (more than) min stake here

    client = NucypherMiddlewareClient()
    response = client.get(node_or_sprout=teacher, path=f"ping", timeout=2)  # TLS certificate login within
    if response.status_code == 200:
        log.info(f'Fetched external IP address from default teacher ({top_teacher_url}).')
        return response.text


def get_external_ip_from_known_nodes(known_nodes, sample_size: int = 3, log: Logger = None):
    if not log:
        log = Logger('whoami')
    sample = random.sample(known_nodes, sample_size)
    for node in sample:
        ip = get_external_ip_from_url_source(url=node.rest_url())
        if ip:
            log.info(f'Fetched external IP address from randomly selected known node(s).')
            return ip


def get_external_ip_from_centralized_source(log: Logger = None) -> str:
    endpoint = 'https://ifconfig.me/'
    ip = get_external_ip_from_url_source(url=endpoint)
    if not log:
        log = Logger('whoami')
    log.info(f'Fetched external IP address from centralized source ({endpoint}).')
    return ip


def determine_external_ip_address(network: str, known_nodes=None) -> str:
    """
    Attempts to automatically get the external IP from the default teacher.
    If the request fails, it falls back to a centralized service.  If the IP address cannot be determined
    for any reason UnknownIPAddress is raised.
    """
    rest_host = None
    if known_nodes:  # primary
        rest_host = get_external_ip_from_known_nodes(known_nodes=known_nodes)
    if not rest_host:  # fallback 1
        rest_host = get_external_ip_from_default_teacher(network=network)
    if not rest_host:  # fallback 2
        rest_host = get_external_ip_from_centralized_source()
    if not rest_host:  # complete cascading failure
        raise UnknownIPAddress('External IP address detection failed')
    return rest_host
