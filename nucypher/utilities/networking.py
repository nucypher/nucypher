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

import click
import requests

from nucypher.cli.literature import CONFIRM_URSULA_IPV4_ADDRESS, COLLECT_URSULA_IPV4_ADDRESS, \
    FORCE_DETECT_URSULA_IP_WARNING
from nucypher.cli.types import IPV4_ADDRESS


class UnknownIPAddress(RuntimeError):
    pass


def get_external_ip_from_centralized_source() -> str:
    ip_request = requests.get('https://ifconfig.me/')
    if ip_request.status_code == 200:
        return ip_request.text
    raise UnknownIPAddress(f"There was an error determining the IP address automatically. "
                           f"(status code {ip_request.status_code})")


def determine_external_ip_address(emitter, force: bool = False) -> str:
    """
    Attempts to automatically get the external IP from ifconfig.me
    If the request fails, it falls back to the standard process.
    """
    try:
        rest_host = get_external_ip_from_centralized_source()
    except UnknownIPAddress:
        if force:
            raise
    else:
        # Interactive
        if not force:
            if not click.confirm(CONFIRM_URSULA_IPV4_ADDRESS.format(rest_host=rest_host)):
                rest_host = click.prompt(COLLECT_URSULA_IPV4_ADDRESS, type=IPV4_ADDRESS)
        else:
            emitter.message(FORCE_DETECT_URSULA_IP_WARNING.format(rest_host=rest_host), color='yellow')

        return rest_host
