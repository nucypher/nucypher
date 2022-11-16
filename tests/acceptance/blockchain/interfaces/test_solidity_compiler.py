

from nucypher.blockchain.eth.deployers import NucypherTokenDeployer
from nucypher.blockchain.eth.sol.compile.compile import multiversion_compile
from nucypher.blockchain.eth.sol.compile.constants import DEFAULT_VERSION_STRING, TEST_MULTIVERSION_CONTRACTS, \
    TEST_SOLIDITY_SOURCE_ROOT, SOLIDITY_SOURCE_ROOT
from nucypher.blockchain.eth.sol.compile.types import SourceBundle


def test_nucypher_contract_compiled(testerchain, test_registry):
    """Ensure that solidity smart contacts are available, post-compile."""
    origin, *everybody_else = testerchain.client.accounts

    token_contract_identifier = NucypherTokenDeployer(registry=test_registry).contract_name
    assert token_contract_identifier in testerchain._raw_contract_cache
    token_data = testerchain._raw_contract_cache[token_contract_identifier]
    assert len(token_data) == 1
    assert DEFAULT_VERSION_STRING in token_data


def test_multi_source_compilation(testerchain):
    bundles = [
        SourceBundle(base_path=SOLIDITY_SOURCE_ROOT),
        SourceBundle(base_path=SOLIDITY_SOURCE_ROOT, other_paths=(TEST_SOLIDITY_SOURCE_ROOT,))
    ]
    interfaces = multiversion_compile(source_bundles=bundles)
    raw_cache = testerchain._raw_contract_cache.copy()
    assert interfaces == raw_cache


def test_multi_versions():
    base_dir = TEST_MULTIVERSION_CONTRACTS
    v1_dir, v2_dir = base_dir / "v1", base_dir / "v2"
    bundles = [
        SourceBundle(base_path=v1_dir),
        SourceBundle(base_path=v2_dir)
    ]
    interfaces = multiversion_compile(source_bundles=bundles)
    assert "VersionTest" in interfaces
    contract_data = interfaces["VersionTest"]
    assert len(contract_data) == 2
    assert "v1.2.3" in contract_data
    assert "v1.1.4" in contract_data
    assert contract_data["v1.2.3"]["devdoc"]['details'] != contract_data["v1.1.4"]["devdoc"]['details']
