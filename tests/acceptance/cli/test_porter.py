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

import os
from pathlib import Path

import pytest

from nucypher.characters.lawful import Ursula
from nucypher.cli.literature import (
    PORTER_BASIC_AUTH_ENABLED,
    PORTER_BASIC_AUTH_REQUIRES_HTTPS,
    PORTER_BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED,
    PORTER_RUN_MESSAGE, PORTER_CORS_ALLOWED_ORIGINS
)
from nucypher.cli.main import nucypher_cli
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.porter.porter import Porter
from tests.constants import TEST_PROVIDER_URI
from tests.utils.ursula import select_test_port


@pytest.fixture(scope="function")
def federated_teacher_uri(mocker, federated_ursulas):
    teacher = list(federated_ursulas)[0]
    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=teacher)
    yield teacher_uri


@pytest.fixture(scope="function")
def blockchain_teacher_uri(mocker, blockchain_ursulas):
    teacher = list(blockchain_ursulas)[0]
    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=teacher)
    yield teacher_uri


def test_federated_porter_cli_run_simple(click_runner, federated_ursulas, federated_teacher_uri):
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    output = result.output
    assert f"Network: {TEMPORARY_DOMAIN}" in output
    assert PORTER_RUN_MESSAGE.format(http_scheme="http", http_port=Porter.DEFAULT_PORT) in output

    # Non-default port
    non_default_port = select_test_port()
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--http-port', non_default_port,
                          '--teacher', federated_teacher_uri)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    output = result.output
    assert f"Network: {TEMPORARY_DOMAIN}" in output
    assert PORTER_RUN_MESSAGE.format(http_scheme="http", http_port=non_default_port) in output


def test_federated_porter_cli_run_teacher_must_be_provided(click_runner, federated_ursulas):
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only')

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code != 0
    assert f"--teacher is required" in result.output


def test_federated_porter_cli_run_tls_filepath_and_certificate(click_runner,
                                                               federated_ursulas,
                                                               tempfile_path,
                                                               temp_dir_path,
                                                               federated_teacher_uri):
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-key-filepath', tempfile_path)  # only tls-key provided
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code != 0  # both --tls-key-filepath and --tls-certificate-filepath must be provided for TLS
    assert PORTER_BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED in result.output

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-certificate-filepath', tempfile_path)  # only certificate provided
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code != 0  # both --tls-key-filepath and --tls-certificate-filepath must be provided for TLS
    assert PORTER_BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED in result.output

    #
    # tls-key and certificate filepaths must exist
    #
    assert Path(tempfile_path).exists()  # temp file exists

    non_existent_path = (Path(temp_dir_path) / 'non_existent_file')
    assert not non_existent_path.exists()
    # tls-key-filepath does not exist
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-certificate-filepath', tempfile_path,
                          '--tls-key-filepath', str(non_existent_path.absolute()))
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code != 0
    output = result.output
    assert f"'--tls-key-filepath': File '{non_existent_path.absolute()}' does not exist" in output

    # tls-certificate-filepath does not exist
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-certificate-filepath', str(non_existent_path.absolute()),
                          '--tls-key-filepath', tempfile_path)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code != 0
    output = result.output
    assert f"'--tls-certificate-filepath': File '{non_existent_path.absolute()}' does not exist" in output


def test_federated_cli_run_https(click_runner, federated_ursulas, temp_dir_path, federated_teacher_uri):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_RUN_MESSAGE.format(http_scheme="https", http_port=Porter.DEFAULT_PORT) in result.output


def test_federated_cli_run_https_with_cors_origin(click_runner,
                                                  federated_ursulas,
                                                  temp_dir_path,
                                                  federated_teacher_uri):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    allow_origins = ".*\.example\.com,.*\.otherexample\.org"

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path,
                          '--allow-origins', allow_origins)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_RUN_MESSAGE.format(http_scheme="https", http_port=Porter.DEFAULT_PORT) in result.output
    assert PORTER_CORS_ALLOWED_ORIGINS.format(allow_origins=allow_origins.split(",")) in result.output


def test_federated_cli_run_https_with_empty_string_cors_origin(click_runner,
                                                               federated_ursulas,
                                                               temp_dir_path,
                                                               federated_teacher_uri):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    empty_string_allow_origins = ""

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path,
                          '--allow-origins', empty_string_allow_origins)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_RUN_MESSAGE.format(http_scheme="https", http_port=Porter.DEFAULT_PORT) in result.output
    # empty string translates to CORS not being enabled - empty origin string provides wild card comparison
    # with just header
    assert PORTER_CORS_ALLOWED_ORIGINS.format(allow_origins='') not in result.output


def test_federated_cli_run_https_basic_auth(click_runner,
                                            federated_ursulas,
                                            federated_teacher_uri,
                                            temp_dir_path,
                                            basic_auth_file):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--federated-only',
                          '--teacher', federated_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path,
                          '--basic-auth-filepath', basic_auth_file)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_BASIC_AUTH_ENABLED in result.output


def test_blockchain_porter_cli_run_simple(click_runner,
                                          blockchain_ursulas,
                                          testerchain,
                                          agency_local_registry,
                                          blockchain_teacher_uri):
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    output = result.output
    assert f"Network: {TEMPORARY_DOMAIN}" in output
    assert f"Provider: {TEST_PROVIDER_URI}" in output
    assert PORTER_RUN_MESSAGE.format(http_scheme="http", http_port=Porter.DEFAULT_PORT) in output

    # Non-default port
    non_default_port = select_test_port()
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--http-port', non_default_port,
                          '--teacher', blockchain_teacher_uri)
    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    output = result.output
    assert f"Network: {TEMPORARY_DOMAIN}" in output
    assert f"Provider: {TEST_PROVIDER_URI}" in output
    assert PORTER_RUN_MESSAGE.format(http_scheme="http", http_port=non_default_port) in output


def test_blockchain_porter_cli_run_provider_required(click_runner,
                                                     blockchain_ursulas,
                                                     testerchain,
                                                     agency_local_registry,
                                                     blockchain_teacher_uri):
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri)

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)

    assert result.exit_code != 0
    assert "--provider is required" in result.output


def test_blockchain_porter_cli_run_network_defaults_to_mainnet(click_runner,
                                                               blockchain_ursulas,
                                                               testerchain,
                                                               agency_local_registry,
                                                               blockchain_teacher_uri):
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri)

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)

    assert result.exit_code != 0
    # there is no 'mainnet' network for decentralized testing
    assert "'mainnet' is not a NuCypher Network" in result.output


def test_blockchain_porter_cli_run_https(click_runner,
                                         blockchain_ursulas,
                                         testerchain,
                                         agency_local_registry,
                                         temp_dir_path,
                                         blockchain_teacher_uri):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path)

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_RUN_MESSAGE.format(http_scheme="https", http_port=Porter.DEFAULT_PORT) in result.output
    # no CORS configured by default; empty origin string provides wild card comparison with just header
    assert PORTER_CORS_ALLOWED_ORIGINS.format(allow_origins='') not in result.output


def test_blockchain_porter_cli_run_https_with_cors_origin(click_runner,
                                                          blockchain_ursulas,
                                                          testerchain,
                                                          agency_local_registry,
                                                          temp_dir_path,
                                                          blockchain_teacher_uri):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    allow_origins = "*"

    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path,
                          '--allow-origins', allow_origins)

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_RUN_MESSAGE.format(http_scheme="https", http_port=Porter.DEFAULT_PORT) in result.output
    assert PORTER_CORS_ALLOWED_ORIGINS.format(allow_origins=[allow_origins]) in result.output


def test_blockchain_porter_cli_run_https_basic_auth(click_runner,
                                                    blockchain_ursulas,
                                                    blockchain_teacher_uri,
                                                    testerchain,
                                                    agency_local_registry,
                                                    temp_dir_path,
                                                    basic_auth_file
                                                    ):
    tls_key_path = Path(temp_dir_path) / 'key.pem'
    _write_random_data(tls_key_path)
    certificate_file_path = Path(temp_dir_path) / 'fullchain.pem'
    _write_random_data(certificate_file_path)

    # Basic Auth requires https - missing both tls parameters
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri,
                          '--basic-auth-filepath', basic_auth_file)

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code != 0
    assert PORTER_BASIC_AUTH_REQUIRES_HTTPS in result.output

    # Basic Auth
    porter_run_command = ('porter', 'run',
                          '--dry-run',
                          '--network', TEMPORARY_DOMAIN,
                          '--provider', TEST_PROVIDER_URI,
                          '--registry-filepath', agency_local_registry.filepath,
                          '--teacher', blockchain_teacher_uri,
                          '--tls-key-filepath', tls_key_path,
                          '--tls-certificate-filepath', certificate_file_path,
                          '--basic-auth-filepath', basic_auth_file)

    result = click_runner.invoke(nucypher_cli, porter_run_command, catch_exceptions=False)
    assert result.exit_code == 0
    assert PORTER_BASIC_AUTH_ENABLED in result.output


def _write_random_data(filepath: Path):
    with filepath.open('wb') as file:
        file.write(os.urandom(24))
