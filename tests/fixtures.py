import contextlib
import json
import os
import shutil
import tempfile
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Tuple
from unittest.mock import PropertyMock

import maya
import pytest
from click.testing import CliRunner
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import to_checksum_address
from nucypher_core.ferveo import AggregatedTranscript, DkgPublicKey, Keypair, Validator
from siwe import SiweMessage
from twisted.internet.task import Clock
from web3 import Web3

import tests
from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.interfaces import (
    BlockchainInterface,
    BlockchainInterfaceFactory,
)
from nucypher.blockchain.eth.signers.software import InMemorySigner, KeystoreSigner
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.cli.config import GroupGeneralConfig
from nucypher.config.characters import (
    AliceConfiguration,
    BobConfiguration,
    UrsulaConfiguration,
)
from nucypher.config.constants import (
    APP_DIR,
    TEMPORARY_DOMAIN_NAME,
)
from nucypher.crypto.ferveo import dkg
from nucypher.crypto.keystore import Keystore
from nucypher.network.nodes import TEACHER_NODES
from nucypher.policy.conditions.auth.evm import EvmAuth
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import RPCCondition
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    ConditionType,
    ReturnValueTest,
)
from nucypher.policy.conditions.time import TimeCondition
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings, Logger
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from nucypher.utilities.task import SimpleTask
from tests.constants import (
    MIN_OPERATOR_SECONDS,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_CUSTOM_INSTALLATION_PATH_2,
    MOCK_ETH_PROVIDER_URI,
    TEMPORARY_DOMAIN,
    TEST_ETH_PROVIDER_URI,
    TESTERCHAIN_CHAIN_ID,
)
from tests.mock.interfaces import MockBlockchain
from tests.mock.performance_mocks import (
    mock_cert_generation,
    mock_cert_loading,
    mock_keep_learning,
    mock_message_verification,
    mock_record_fleet_state,
    mock_remember_node,
    mock_rest_app_creation,
    mock_verify_node,
)
from tests.utils.blockchain import ReservedTestAccountManager
from tests.utils.config import (
    make_alice_test_configuration,
    make_bob_test_configuration,
    make_ursula_test_configuration,
)
from tests.utils.middleware import (
    MockRestMiddleware,
    MockRestMiddlewareForLargeFleetTests,
)
from tests.utils.policy import generate_random_label
from tests.utils.ursula import (
    MOCK_KNOWN_URSULAS_CACHE,
    make_random_ursulas,
    make_reserved_ursulas,
    select_test_port,
)

test_logger = Logger("test-logger")

# defer.setDebugging(True)


#
# Temporary
#


@pytest.fixture(scope="function")
def tempfile_path():
    fd, path = tempfile.mkstemp()
    path = Path(path)
    yield path
    os.close(fd)
    path.unlink()


@pytest.fixture(scope="module")
def temp_dir_path():
    temp_dir = tempfile.TemporaryDirectory(prefix="nucypher-test-")
    yield Path(temp_dir.name)
    temp_dir.cleanup()


@pytest.fixture(scope="function", autouse=True)
def mock_write_wallet_to_file(mocker):
    return mocker.patch.object(Keystore, "_write_wallet")


#
# Accounts
#


@pytest.fixture(scope="session", autouse=True)
def accounts():
    """a la ape"""
    return ReservedTestAccountManager()


@pytest.fixture(scope="module")
def random_account():
    key = Account.create(extra_entropy="lamborghini mercy")
    account = Account.from_key(private_key=key.key)
    return account


@pytest.fixture(scope="module")
def random_address(random_account):
    return random_account.address


#
# Character Configurations
#


@pytest.fixture(scope="module")
def ursula_test_config(test_registry, temp_dir_path):
    config = make_ursula_test_configuration(
        eth_endpoint=TEST_ETH_PROVIDER_URI,
        polygon_endpoint=TEST_ETH_PROVIDER_URI,
        test_registry=test_registry,
        rest_port=select_test_port(),
    )
    yield config
    config.cleanup()
    for k in list(MOCK_KNOWN_URSULAS_CACHE.keys()):
        del MOCK_KNOWN_URSULAS_CACHE[k]


@pytest.fixture(scope="module")
def alice_test_config(ursulas, accounts, test_registry):
    config = make_alice_test_configuration(
        eth_endpoint=TEST_ETH_PROVIDER_URI,
        polygon_endpoint=TEST_ETH_PROVIDER_URI,
        known_nodes=ursulas,
        checksum_address=accounts.alice_account,
        test_registry=test_registry,
    )
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def bob_test_config(accounts, test_registry):
    config = make_bob_test_configuration(
        eth_endpoint=TEST_ETH_PROVIDER_URI,
        test_registry=test_registry,
        checksum_address=accounts.bob_account,
    )
    yield config
    config.cleanup()


#
# Policies
#


@pytest.fixture(scope="module")
def idle_policy(testerchain, alice, bob):
    """Creates a Policy, in a manner typical of how Alice might do it, with a unique label"""
    random_label = generate_random_label()
    expiration = maya.now() + timedelta(days=1)
    threshold, shares = 3, 5
    price = alice.pre_payment_method.quote(
        expiration=expiration.epoch, shares=shares
    ).value  # TODO: use default quote option
    policy = alice.create_policy(
        bob,
        label=random_label,
        value=price,
        threshold=threshold,
        shares=shares,
        expiration=expiration,
    )
    return policy


@pytest.fixture(scope="module")
def enacted_policy(idle_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualified Ursulas; she crafts an offer for them.

    # value and expiration were set when creating idle_policy already
    # cannot set them again
    # deposit = NON_PAYMENT(b"0000000")
    # contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware(eth_endpoint=TEST_ETH_PROVIDER_URI)

    # REST call happens here, as does population of TreasureMap.
    enacted_policy = idle_policy.enact(
        network_middleware=network_middleware, ursulas=list(ursulas)
    )
    return enacted_policy


@pytest.fixture(scope="module")
def treasure_map(enacted_policy, bob):
    """
    The unencrypted treasure map corresponding to the one in `enacted_policy`
    """
    yield bob._decrypt_treasure_map(
        enacted_policy.treasure_map, enacted_policy.publisher_verifying_key
    )


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_policy):
    class _CapsuleSideChannel:
        def __init__(self):
            self.enrico = Enrico(encrypting_key=enacted_policy.public_key)
            self.messages = []
            self.plaintexts = []
            self.plaintext_passthrough = False

        def __call__(self):
            message = "Welcome to flippering number {}.".format(
                len(self.messages)
            ).encode()
            message_kit = self.enrico.encrypt_for_pre(message)
            self.messages.append((message_kit, self.enrico))
            if self.plaintext_passthrough:
                self.plaintexts.append(message)
            return message_kit

        def reset(self, plaintext_passthrough=False):
            self.enrico = Enrico(encrypting_key=enacted_policy.public_key)
            self.messages.clear()
            self.plaintexts.clear()
            self.plaintext_passthrough = plaintext_passthrough
            return self(), self.enrico

    return _CapsuleSideChannel()


@pytest.fixture(scope="module")
def random_policy_label():
    yield generate_random_label()


#
# Alice, Bob, and Ursula
#


@pytest.fixture(scope="module")
def alice(alice_test_config, accounts):
    alice = alice_test_config.produce(
        signer=accounts.get_account_signer(accounts.alice_account)
    )
    yield alice
    alice.disenchant()


@pytest.fixture(scope="module")
def bob(bob_test_config, accounts):
    bob = bob_test_config.produce(
        polygon_endpoint=TEST_ETH_PROVIDER_URI,
        signer=accounts.get_account_signer(accounts.bob_account),
    )
    yield bob
    bob.disenchant()


@pytest.fixture(scope="function")
def lonely_ursula_maker(ursula_test_config, accounts):
    class _PartialUrsulaMaker:
        _partial = partial(
            make_reserved_ursulas,
            accounts=accounts,
            ursula_config=ursula_test_config,
            know_each_other=False,
        )
        _made = []

        def __call__(self, *args, **kwargs):
            ursulas = self._partial(*args, **kwargs)
            self._made.extend(ursulas)
            return ursulas

        def clean(self):
            for ursula in self._made:
                ursula.stop()
            for ursula in self._made:
                del MOCK_KNOWN_URSULAS_CACHE[ursula.rest_interface.port]
            for ursula in self._made:
                ursula._finalize()

    _maker = _PartialUrsulaMaker()
    yield _maker
    _maker.clean()


#
# Blockchain
#
@pytest.fixture(scope="module")
def mock_registry_sources(module_mocker):
    with tests.utils.registry.mock_registry_sources(module_mocker):
        yield


@pytest.fixture(scope="module")
def mock_testerchain() -> MockBlockchain:
    BlockchainInterfaceFactory._interfaces = dict()
    testerchain = MockBlockchain()
    BlockchainInterfaceFactory.register_interface(interface=testerchain)
    yield testerchain


@pytest.fixture()
def light_ursula(temp_dir_path, random_account, mocker):
    mocker.patch.object(KeystoreSigner, "_get_signer", return_value=random_account)
    pre_payment_method = SubscriptionManagerPayment(
        blockchain_endpoint=MOCK_ETH_PROVIDER_URI, domain=TEMPORARY_DOMAIN_NAME
    )

    mocker.patch.object(
        Operator, "get_staking_provider_address", return_value=random_account.address
    )

    ursula = Ursula(
        rest_host=LOOPBACK_ADDRESS,
        rest_port=select_test_port(),
        domain=TEMPORARY_DOMAIN_NAME,
        pre_payment_method=pre_payment_method,
        checksum_address=random_account.address,
        operator_address=random_account.address,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
        signer=KeystoreSigner(path=temp_dir_path),
        condition_blockchain_endpoints={TESTERCHAIN_CHAIN_ID: [MOCK_ETH_PROVIDER_URI]},
    )
    return ursula


@pytest.fixture(scope="module")
def policy_rate():
    rate = Web3.to_wei(21, "gwei")
    return rate


@pytest.fixture(scope="module")
def policy_value(policy_rate):
    value = policy_rate * MIN_OPERATOR_SECONDS
    return value


#
# Test logging
#


@pytest.fixture(autouse=True, scope="function")
def log_in_and_out_of_test(request):
    test_name = request.node.name
    module_name = request.module.__name__

    test_logger.info(f"Starting {module_name}.py::{test_name}")
    yield
    test_logger.info(f"Finalized {module_name}.py::{test_name}")


@pytest.fixture(scope="session")
def get_random_checksum_address():
    def _get_random_checksum_address():
        canonical_address = os.urandom(20)
        checksum_address = to_checksum_address(canonical_address)
        return checksum_address

    return _get_random_checksum_address


@pytest.fixture(scope="module")
def fleet_of_highperf_mocked_ursulas(ursula_test_config, request, testerchain):
    mocks = (
        mock_cert_loading,
        mock_rest_app_creation,
        mock_cert_generation,
        mock_remember_node,
        mock_message_verification,
    )

    try:
        quantity = request.param
    except AttributeError:
        quantity = 5000  # Bigass fleet by default; that's kinda the point.

    with GlobalLoggerSettings.pause_all_logging_while():
        with contextlib.ExitStack() as stack:
            for mock in mocks:
                stack.enter_context(mock)

            _ursulas = make_random_ursulas(
                ursula_config=ursula_test_config,
                quantity=quantity,
                know_each_other=False,
            )
            all_ursulas = {u.checksum_address: u for u in _ursulas}

            for ursula in _ursulas:
                # FIXME #2588: FleetSensor should not own fully-functional Ursulas.
                # It only needs to see whatever public info we can normally get via REST.
                # Also sharing mutable Ursulas like that can lead to unpredictable results.
                ursula.known_nodes.current_state._nodes = all_ursulas
                ursula.known_nodes.current_state.checksum = (
                    b"This is a fleet state checksum..".hex()
                )

    yield _ursulas

    for ursula in _ursulas:
        del MOCK_KNOWN_URSULAS_CACHE[ursula.rest_interface.port]


@pytest.fixture(scope="module")
def highperf_mocked_alice(
    fleet_of_highperf_mocked_ursulas,
    monkeymodule,
    accounts,
):
    config = AliceConfiguration(
        dev_mode=True,
        domain=TEMPORARY_DOMAIN_NAME,
        eth_endpoint=TEST_ETH_PROVIDER_URI,
        checksum_address=accounts.alice_account,
        network_middleware=MockRestMiddlewareForLargeFleetTests(
            eth_endpoint=TEST_ETH_PROVIDER_URI
        ),
        abort_on_learning_error=True,
        save_metadata=False,
        reload_metadata=False,
    )

    with mock_verify_node, mock_message_verification, mock_keep_learning:
        alice = config.produce(known_nodes=list(fleet_of_highperf_mocked_ursulas)[:1])
    yield alice
    # TODO: Where does this really, truly belong?
    alice._learning_task.stop()


@pytest.fixture(scope="module")
def highperf_mocked_bob(fleet_of_highperf_mocked_ursulas):
    config = BobConfiguration(
        dev_mode=True,
        eth_endpoint=TEST_ETH_PROVIDER_URI,
        domain=TEMPORARY_DOMAIN_NAME,
        network_middleware=MockRestMiddlewareForLargeFleetTests(
            eth_endpoint=TEST_ETH_PROVIDER_URI
        ),
        abort_on_learning_error=True,
        save_metadata=False,
        reload_metadata=False,
    )

    with mock_verify_node, mock_record_fleet_state, mock_keep_learning:
        bob = config.produce(known_nodes=list(fleet_of_highperf_mocked_ursulas)[:1])
    yield bob
    bob._learning_task.stop()
    return bob


#
# CLI
#


@pytest.fixture(scope="function")
def test_emitter(mocker):
    # Note that this fixture does not capture console output.
    # Whether the output is captured or not is controlled by
    # the usage of the (built-in) `capsys` fixture or global PyTest run settings.
    return StdoutEmitter()


@pytest.fixture(scope="module")
def click_runner():
    runner = CliRunner()
    yield runner


@pytest.fixture(scope="module")
def nominal_configuration_fields():
    config = UrsulaConfiguration(
        dev_mode=True,
        domain=TEMPORARY_DOMAIN_NAME,
        eth_endpoint=TEST_ETH_PROVIDER_URI,
    )
    config_fields = config.static_payload()
    yield tuple(config_fields.keys())
    del config


@pytest.fixture(scope="module")
def custom_filepath():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    yield _custom_filepath
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)


@pytest.fixture(scope="module")
def custom_filepath_2():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH_2
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    try:
        yield _custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(_custom_filepath, ignore_errors=True)


@pytest.fixture(scope="module")
def worker_configuration_file_location(custom_filepath) -> Path:
    _configuration_file_location = (
        MOCK_CUSTOM_INSTALLATION_PATH / UrsulaConfiguration.generate_filename()
    )
    return _configuration_file_location


@pytest.fixture(autouse=True)
def mock_teacher_nodes(mocker):
    mock_nodes = tuple(u.rest_url() for u in MOCK_KNOWN_URSULAS_CACHE.values())[0:2]
    mocker.patch.dict(TEACHER_NODES, {TEMPORARY_DOMAIN: mock_nodes}, clear=True)


@pytest.fixture(autouse=True)
def disable_interactive_keystore_generation(mocker):
    # Do not notify or confirm mnemonic seed words during tests normally
    mocker.patch.object(Keystore, "_confirm_generate")


#
# Web Auth
#
@pytest.fixture(scope="module")
def basic_auth_file(temp_dir_path):
    basic_auth = Path(temp_dir_path) / "htpasswd"
    with basic_auth.open("w") as f:
        # username: "admin", password: "admin"
        f.write("admin:$apr1$hlEpWVoI$0qjykXrvdZ0yO2TnBggQO0\n")
    yield basic_auth
    basic_auth.unlink()


@pytest.fixture(scope="module")
def mock_rest_middleware():
    return MockRestMiddleware(eth_endpoint=TEST_ETH_PROVIDER_URI)


#
# Conditions
#


@pytest.fixture(scope="session")
def conditions_test_data():
    test_conditions = Path(tests.__file__).parent / "data" / "test_conditions.json"
    with open(test_conditions, "r") as file:
        data = json.loads(file.read())
    for name, condition in data.items():
        if condition.get("chain"):
            condition["chain"] = TESTERCHAIN_CHAIN_ID
    return data


@pytest.fixture
def time_condition():
    condition = TimeCondition(
        chain=TESTERCHAIN_CHAIN_ID, return_value_test=ReturnValueTest(">", 0)
    )
    return condition


@pytest.fixture
def compound_blocktime_lingo():
    return {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "and",
            "operands": [
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {
                        "value": 99999999999999999,
                        "comparator": "<",
                    },
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
            ],
        },
    }


@pytest.fixture
def rpc_condition():
    condition = RPCCondition(
        method="eth_getBalance",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", Web3.to_wei(1_000_000, "ether")),
        parameters=[USER_ADDRESS_CONTEXT],
    )
    return condition


@pytest.fixture(scope="function")
def valid_eip712_auth_message():
    signer = Account.create()
    account = signer.address

    data = {
        "primaryType": "Wallet",
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "salt", "type": "bytes32"},
            ],
            "Wallet": [
                {"name": "address", "type": "string"},
                {"name": "blockNumber", "type": "uint256"},
                {"name": "blockHash", "type": "bytes32"},
                {"name": "signatureText", "type": "string"},
            ],
        },
        "domain": {
            "name": "tDec",
            "version": "1",
            "chainId": 80001,
            "salt": "0x3e6365d35fd4e53cbc00b080b0742b88f8b735352ea54c0534ed6a2e44a83ff0",
        },
        "message": {
            "address": f"{account}",
            "blockNumber": 28117088,
            "blockHash": "0x104dfae58be4a9b15d59ce447a565302d5658914f1093f10290cd846fbe258b7",
            "signatureText": f"I'm the owner of address {account} as of block number 28117088",
        },
    }
    signable_message = encode_typed_data(full_message=data)
    signature = signer.sign_message(signable_message=signable_message)

    auth_message = {
        "signature": f"{signature.signature.hex()}",
        "address": f"{account}",
        "scheme": "EIP712",
        "typedData": data,
    }

    return auth_message


@pytest.fixture(scope="function")
def valid_eip4361_auth_message():
    signer = InMemorySigner()
    siwe_message_data = {
        "domain": "login.xyz",
        "address": f"{signer.accounts[0]}",
        "statement": "Sign-In With Ethereum Example Statement",
        "uri": "https://login.xyz",
        "version": "1",
        "nonce": "bTyXgcQxn2htgkjJn",
        "chain_id": 1,
        "issued_at": f"{maya.now().iso8601()}",
    }
    siwe_message = SiweMessage(**siwe_message_data).prepare_message()
    signature = signer.sign_message(
        account=signer.accounts[0], message=siwe_message.encode()
    )
    auth_message = {
        "signature": f"{signature.hex()}",
        "address": f"{signer.accounts[0]}",
        "scheme": f"{EvmAuth.AuthScheme.EIP4361.value}",
        "typedData": f"{siwe_message}",
    }

    return auth_message


@pytest.fixture(scope="session", autouse=True)
def clock():
    """Distorts the space-time continuum.  Use with caution."""
    clock = Clock()
    SimpleTask.CLOCK = clock
    SimpleTask.INTERVAL = 1
    return clock


@pytest.fixture(scope="module")
def ursulas(accounts, ursula_test_config, staking_providers):
    if MOCK_KNOWN_URSULAS_CACHE:
        # TODO: Is this a safe assumption / test behaviour?
        # raise RuntimeError("Ursulas cache was unclear at fixture loading time.  Did you use one of the ursula maker functions without cleaning up?")
        MOCK_KNOWN_URSULAS_CACHE.clear()

    _ursulas = make_reserved_ursulas(
        accounts=accounts,
        ursula_config=ursula_test_config,
        know_each_other=True,
    )
    for u in _ursulas:
        u.synchronous_query_timeout = 0.01  # We expect to never have to wait for content that is actually on-chain during tests.

    _ports_to_remove = [ursula.rest_interface.port for ursula in _ursulas]
    yield _ursulas

    for port in _ports_to_remove:
        del MOCK_KNOWN_URSULAS_CACHE[port]

    for u in _ursulas:
        u.stop()
        u._finalize()

    # Pytest will hold on to this object, need to clear it manually.
    # See https://github.com/pytest-dev/pytest/issues/5642
    _ursulas.clear()


@pytest.fixture(scope="session")
def dkg_public_key_data(
    get_random_checksum_address,
) -> Tuple[AggregatedTranscript, DkgPublicKey]:
    ritual_id = 0
    num_shares = 4
    threshold = 3
    validators = []
    for i in range(0, num_shares):
        validators.append(
            Validator(
                address=get_random_checksum_address(),
                public_key=Keypair.random().public_key(),
            )
        )

    validators.sort(key=lambda x: x.address)  # must be sorted

    transcripts = []
    for validator in validators:
        transcript = dkg.generate_transcript(
            ritual_id=ritual_id,
            me=validator,
            shares=num_shares,
            threshold=threshold,
            nodes=validators,
        )
        transcripts.append((validator, transcript))

    aggregate_transcript, public_key = dkg.aggregate_transcripts(
        ritual_id=ritual_id,
        me=validators[0],
        shares=num_shares,
        threshold=threshold,
        transcripts=transcripts,
    )

    return aggregate_transcript, public_key


@pytest.fixture(scope="session")
def dkg_public_key(dkg_public_key_data) -> DkgPublicKey:
    _, dkg_public_key = dkg_public_key_data
    return dkg_public_key


@pytest.fixture(scope="session")
def aggregated_transcript(dkg_public_key_data) -> AggregatedTranscript:
    aggregated_transcript, _ = dkg_public_key_data
    return aggregated_transcript


#
# DKG Ritual Aggregation
#
@pytest.fixture(scope="module", autouse=True)
def mock_operator_aggregation_delay(module_mocker):
    module_mocker.patch(
        "nucypher.blockchain.eth.actors.Operator.AGGREGATION_SUBMISSION_MAX_DELAY",
        PropertyMock(return_value=1),
    )


@pytest.fixture
def mock_async_hooks(mocker):
    hooks = BlockchainInterface.AsyncTxHooks(
        on_broadcast=mocker.Mock(),
        on_broadcast_failure=mocker.Mock(),
        on_fault=mocker.Mock(),
        on_finalized=mocker.Mock(),
        on_insufficient_funds=mocker.Mock(),
    )

    return hooks


@pytest.fixture(scope="session", autouse=True)
def mock_halt_reactor(session_mocker):
    session_mocker.patch.object(Ursula, "halt_reactor")


@pytest.fixture(scope="session")
def temp_config_root():
    return Path("/tmp/nucypher-test")


@pytest.fixture(scope="session", autouse=True)
def mock_default_config_root(session_mocker, temp_config_root):
    real_default_config_root = Path(APP_DIR.user_data_dir)
    if real_default_config_root.exists():
        if os.getenv("GITHUB_ACTIONS") == "true":
            shutil.rmtree(real_default_config_root)
        else:
            raise RuntimeError(
                f"{real_default_config_root} already exists.  It is not permitted to run tests in an (production) "
                f"environment where this directory exists.  Please remove it before running tests."
            )
    session_mocker.patch(
        "nucypher.config.constants.DEFAULT_CONFIG_ROOT", temp_config_root
    )
    session_mocker.patch.object(GroupGeneralConfig, "config_root", temp_config_root)


@pytest.fixture(scope="function", autouse=True)
def clear_config_root(temp_config_root):
    if temp_config_root.exists():
        print(f"Removing {temp_config_root}")
        shutil.rmtree(Path("/tmp/nucypher-test"))
    yield
    if Path(APP_DIR.user_data_dir).exists():
        raise RuntimeError(
            f"{APP_DIR.user_data_dir} was used by a test.  This is not permitted, please mock."
        )


@pytest.fixture(scope="session", autouse=True)
def mock_default_rpc_endpoint_fetch(session_mocker):
    session_mocker.patch(
        "nucypher.blockchain.eth.utils.get_default_rpc_endpoints",
        return_value={TESTERCHAIN_CHAIN_ID: [TEST_ETH_PROVIDER_URI]},
    )
