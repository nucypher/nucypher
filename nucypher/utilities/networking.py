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


import requests
from requests.exceptions import RequestException, HTTPError
from typing import Union

from nucypher.network.middleware import RestMiddleware


class UnknownIPAddress(RuntimeError):
    pass


RequestErrors = (
    # https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions
    ConnectionError,
    TimeoutError,
    RequestException,
    HTTPError
)


def get_external_ip_from_url_source(url: str) -> Union[str, None]:
    try:
        response = requests.get(url)
    except RequestErrors:
        return None
    if response.status_code == 200:
        return response.text


def get_external_ip_from_default_teacher(network: str) -> Union[str, None]:
    endpoint = f'{RestMiddleware.TEACHER_NODES[network]}/ping'
    ip = get_external_ip_from_url_source(url=endpoint)
    return ip


def get_external_ip_from_centralized_source() -> str:
    endpoint = 'https://ifconfig.me/'
    ip = get_external_ip_from_url_source(url=endpoint)
    return ip


def determine_external_ip_address(network: str) -> str:
    """
    Attempts to automatically get the external IP from the default teacher.
    If the request fails, it falls back to a centralized service.  If the IP address cannot be determined
    for any reason UnknownIPAddress is raised.
    """
    rest_host = get_external_ip_from_default_teacher(network=network)
    if not rest_host:  # fallback
        rest_host = get_external_ip_from_centralized_source()
    if not rest_host:  # fallback failure
        raise UnknownIPAddress('External IP address detection failed')
    return rest_host
