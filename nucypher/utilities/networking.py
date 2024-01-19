import random
from http import HTTPStatus
from ipaddress import AddressValueError, IPv4Address, IPv6Address, ip_address
from typing import List, Optional, Union

import requests
from flask import Request
from requests.exceptions import HTTPError, RequestException

from nucypher.acumen.perception import FleetSensor
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.config.storages import LocalFileBasedNodeStorage
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import NucypherMiddlewareClient, RestMiddleware
from nucypher.utilities.logging import Logger


class UnknownIPAddress(RuntimeError):
    pass


class InvalidOperatorIP(RuntimeError):
    """Raised when an Ursula is using an invalid IP address for it's server."""


CENTRALIZED_IP_ORACLE_URL = 'https://ifconfig.me/'

LOOPBACK_ADDRESS = '127.0.0.1'

RequestErrors = (
    # https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions
    ConnectionError,
    TimeoutError,
    RequestException,
    HTTPError
)

RESERVED_IP_ADDRESSES = (
    '0.0.0.0',
    LOOPBACK_ADDRESS,
    '1.2.3.4'
)

IP_DETECTION_LOGGER = Logger('external-ip-detection')


def validate_operator_ip(ip: str) -> None:
    if ip in RESERVED_IP_ADDRESSES:
        raise InvalidOperatorIP(f"{ip} is not a valid or permitted operator IP address. "
                                f"Verify the 'rest_host' configuration value is set to the "
                                f"external IPV4 address")


def _request(url: str, certificate=None) -> Union[str, None]:
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
    if response.status_code == HTTPStatus.OK:
        return response.text


def _request_from_node(
    teacher,
    eth_endpoint: str,
    client: Optional[NucypherMiddlewareClient] = None,
    timeout: int = 2,
    log: Logger = IP_DETECTION_LOGGER,
) -> Union[str, None]:
    if not client:
        client = NucypherMiddlewareClient(eth_endpoint=eth_endpoint)
    try:
        response = client.get(
            node_or_sprout=teacher, path="ping", timeout=timeout
        )  # TLS certificate logic within
    except RestMiddleware.UnexpectedResponse:
        # 404, 405, 500, All server response codes handled by will be caught here.
        return  # Default teacher does not support this request - just move on.
    except NodeSeemsToBeDown:
        # This node is unreachable.  Move on.
        return
    if response.status_code == HTTPStatus.OK:
        try:
            ip = str(ip_address(response.text))
        except ValueError:
            error = f'Teacher {teacher} returned an invalid IP response; Got {response.text}'
            raise UnknownIPAddress(error)
        log.info(f'Fetched external IP address ({ip}) from teacher ({teacher}).')
        return ip
    else:
        # Something strange happened... move on anyways.
        log.debug(f'Failed to get external IP from teacher node ({teacher} returned {response.status_code})')


def get_external_ip_from_default_teacher(
    domain: str,
    eth_endpoint: str,
    registry: Optional[ContractRegistry] = None,
    log: Logger = IP_DETECTION_LOGGER,
) -> Union[str, None]:
    # Prevents circular imports
    from nucypher.characters.lawful import Ursula
    from nucypher.network.nodes import TEACHER_NODES

    base_error = 'Cannot determine IP using default teacher'

    if domain not in TEACHER_NODES:
        log.debug(f'{base_error}: Unknown domain "{domain}".')
        return

    node_storage = LocalFileBasedNodeStorage()
    Ursula.set_cert_storage_function(node_storage.store_node_certificate)

    external_ip = None
    for teacher_uri in TEACHER_NODES[domain]:
        try:
            teacher = Ursula.from_teacher_uri(
                teacher_uri=teacher_uri, eth_endpoint=eth_endpoint, min_stake=0
            )  # TODO: Handle customized min stake here.
            # TODO: Pass registry here to verify stake (not essential here since it's a hardcoded node)
            external_ip = _request_from_node(teacher=teacher, eth_endpoint=eth_endpoint)
            # Found a reachable teacher, return from loop
            if external_ip:
                break
        except NodeSeemsToBeDown:
            # Teacher is unreachable, try next one
            continue

    if not external_ip:
        log.debug(f'{base_error}: No teacher available for domain "{domain}".')
        return

    return external_ip


def get_external_ip_from_known_nodes(
    known_nodes: FleetSensor,
    eth_endpoint: str,
    sample_size: int = 3,
    log: Logger = IP_DETECTION_LOGGER,
) -> Union[str, None]:
    """
    Randomly select a sample of peers to determine the external IP address
    of this host. The first node to reply successfully will be used.
    # TODO: Parallelize the requests and compare results.
    """
    if len(known_nodes) < sample_size:
        return  # There are too few known nodes
    sample = random.sample(list(known_nodes), sample_size)
    client = NucypherMiddlewareClient(eth_endpoint=eth_endpoint)
    for node in sample:
        ip = _request_from_node(teacher=node, client=client, eth_endpoint=eth_endpoint)
        if ip:
            log.info(f'Fetched external IP address ({ip}) from randomly selected known nodes.')
            return ip


def get_external_ip_from_centralized_source(log: Logger = IP_DETECTION_LOGGER) -> Union[str, None]:
    """Use hardcoded URL to determine the external IP address of this host."""
    ip = _request(url=CENTRALIZED_IP_ORACLE_URL)
    if ip:
        log.info(f'Fetched external IP address ({ip}) from centralized source ({CENTRALIZED_IP_ORACLE_URL}).')
    return ip


def determine_external_ip_address(
    domain: str, eth_endpoint: str, known_nodes: FleetSensor = None
) -> str:
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
        rest_host = get_external_ip_from_known_nodes(
            known_nodes=known_nodes, eth_endpoint=eth_endpoint
        )

    # fallback 1
    if not rest_host:
        rest_host = get_external_ip_from_default_teacher(
            domain=domain, eth_endpoint=eth_endpoint
        )

    # fallback 2
    if not rest_host:
        rest_host = get_external_ip_from_centralized_source()

    # complete failure!
    if not rest_host:
        raise UnknownIPAddress('External IP address detection failed')

    return rest_host


def _is_valid_ipv4(ip: str) -> bool:
    try:
        ip = ip_address(ip.strip())
        return isinstance(ip, IPv4Address) and ip.is_global
    except AddressValueError:
        return False


def _ipv4_to_ipv6(ip: str) -> Optional[str]:
    try:
        ip = ip_address(ip.strip())
        if isinstance(ip, IPv6Address) and ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
    except AddressValueError:
        return None
    return None


def _ip_sources(request: Request, trusted_proxies: Optional[List[str]] = None) -> str:
    if not trusted_proxies:
        trusted_proxies = []
    for header in ["X-Forwarded-For", "X-Real-IP"]:
        if header in request.headers:
            if trusted_proxies and (request.remote_addr not in trusted_proxies):
                yield None  # Do not trust this request
            for ip in request.headers[header].split(","):
                yield ip
    yield request.remote_addr


def get_request_public_ipv4(
    request: Request, trusted_proxies: Optional[List[str]] = None
) -> Optional[str]:
    """
    If the request is forwarded from a proxy, the first global IP address in the chain is returned.
    'X-Forwarded-For' (XFF) https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Forwarded-For#selecting_an_ip_address

    If XFF is not present in the request headers, this method also checks for 'X-Real-IP',
    a popular non-standard header conventionally configured in some proxies like nginx.

    Finally, if neither XFF nor X-Real-IP are present, the request is assumed to be
    direct and the remote address is returned.

    In all cases, tests that the IPv4 range is global. RFC 1918 privately designated
    address ranges must not be returned.
    https://www.ietf.org/rfc/rfc1918.txt

    Optionally, a list of trusted proxies can be provided to help mitigate spoofing attacks.
    """
    for ip_str in _ip_sources(request=request, trusted_proxies=trusted_proxies):
        ipv4_address = _ipv4_to_ipv6(ip_str)
        if ipv4_address and _is_valid_ipv4(ipv4_address):
            return ipv4_address
