import contextlib
import os
import socket
from threading import Lock
from typing import Iterable, List, Optional

from cryptography.x509 import Certificate
from eth_utils import to_checksum_address
from web3 import HTTPProvider

from nucypher.blockchain.eth.signers import InMemorySigner, Signer
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.policy.conditions.utils import ConditionProviderManager
from tests.constants import TESTERCHAIN_CHAIN_ID
from tests.utils.blockchain import ReservedTestAccountManager


class __ActivePortCache:
    """Thread-safe cache for storing current active ports."""
    def __init__(self):
        self._lock = Lock()
        self.active_ports = set()

    def add_port_if_not_already_active(self, port: int) -> bool:
        """
        Atomically check if port is not already active, and if so store port and return True;
        otherwise return False if port is already active.
        """
        with self._lock:
            # check port is active and add (if not already active) atomically
            if port in self.active_ports:
                # port already active; don't add
                return False

            self.active_ports.add(port)
            return True


__ACTIVE_PORTS = __ActivePortCache()


def select_test_port() -> int:
    """
    Search for a network port that is open at the time of the call;
    Verify that the port is not the same as the default Ursula running port.

    Note: There is no guarantee that the returned port will still be available later.
    """

    closed_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with contextlib.closing(closed_socket) as open_socket:
        open_socket.bind(('localhost', 0))
        port = open_socket.getsockname()[1]
        # active ports check should be last and short-circuited using or
        if (
            port > 64000
            or port == UrsulaConfiguration.DEFAULT_REST_PORT
            or not __ACTIVE_PORTS.add_port_if_not_already_active(port)
        ):
            # invalid port; retry
            return select_test_port()

        open_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return port


def make_reserved_ursulas(
    accounts: ReservedTestAccountManager,
    ursula_config: UrsulaConfiguration,
    know_each_other: bool = True,
    quantity: Optional[int] = None,
    **ursula_overrides
):
    num_values = quantity or accounts.NUMBER_OF_URSULAS_IN_TESTS

    staking_providers = accounts.staking_providers_accounts[:num_values]
    operator_signers = [
        accounts.get_account_signer(operator_address)
        for operator_address in accounts.ursulas_accounts[:num_values]
    ]
    return make_ursulas(
        ursula_config,
        staking_providers,
        operator_signers,
        know_each_other,
        **ursula_overrides
    )


def make_random_ursulas(
    ursula_config: UrsulaConfiguration,
    quantity: int,
    know_each_other: bool = True,
    **ursula_overrides
):
    staking_providers = [
        to_checksum_address("0x" + os.urandom(20).hex()) for _ in range(quantity)
    ]
    operator_signers = [InMemorySigner() for _ in range(quantity)]
    return make_ursulas(
        ursula_config,
        staking_providers,
        operator_signers,
        know_each_other,
        **ursula_overrides
    )


def make_ursulas(
    ursula_config: UrsulaConfiguration,
    staking_provider_addresses: Iterable[str],
    operator_signers: Iterable[Signer],
    know_each_other: bool = True,
    **ursula_overrides
):
    providers_and_operators = list(zip(staking_provider_addresses, operator_signers))
    ursulas = list()

    for staking_provider_address, operator_signer in providers_and_operators:
        ursula = ursula_config.produce(
            checksum_address=staking_provider_address,
            operator_address=operator_signer.accounts[0],
            rest_port=select_test_port(),
            signer=operator_signer,
            **ursula_overrides
        )

        ursula.set_provider_public_key()

        ursulas.append(ursula)

        # Store this Ursula in our global testing cache.
        MOCK_KNOWN_URSULAS_CACHE[ursula.rest_interface.port] = ursula

    if know_each_other:
        # Bootstrap the network
        for ursula_to_teach in ursulas:
            for ursula_to_learn_about in ursulas:
                # FIXME #2588: FleetSensor should not own fully-functional Ursulas.
                # It only needs to see whatever public info we can normally get via REST.
                # Also sharing mutable Ursulas like that can lead to unpredictable results.
                ursula_to_teach.remember_node(ursula_to_learn_about)

    return ursulas

def start_pytest_ursula_services(ursula: Ursula) -> Certificate:
    """
    Takes an ursula and starts its learning
    services when running tests with pytest twisted.
    """

    node_deployer = ursula.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    certificate_as_deployed = node_deployer.cert.to_cryptography()
    return certificate_as_deployed


def mock_permitted_multichain_connections(mocker) -> List[int]:
    ids = [
        TESTERCHAIN_CHAIN_ID,
        TESTERCHAIN_CHAIN_ID + 1,
        TESTERCHAIN_CHAIN_ID + 2,
        123456789,
    ]
    return ids


def setup_multichain_ursulas(chain_ids: List[int], ursulas: List[Ursula]) -> None:
    base_uri = "tester://multichain.{}"
    base_fallback_uri = "tester://multichain.fallback.{}"
    blockchain_endpoints = [base_uri.format(i) for i in range(len(chain_ids))]
    fallback_blockchain_endpoints = [
        base_fallback_uri.format(i) for i in range(len(chain_ids))
    ]
    mocked_condition_providers = ConditionProviderManager(
        {
            cid: [HTTPProvider(uri), HTTPProvider(furi)]
            for cid, uri, furi in zip(
                chain_ids, blockchain_endpoints, fallback_blockchain_endpoints
            )
        }
    )
    for ursula in ursulas:
        ursula.condition_provider_manager = mocked_condition_providers


MOCK_KNOWN_URSULAS_CACHE = dict()
