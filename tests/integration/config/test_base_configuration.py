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

import json

import os
from pathlib import Path

import pytest
import shutil

from nucypher.config.base import BaseConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT

#
# Local Test Constants
#

configuration_name = 'something'
expected_extension = 'json'
configuration_value = 're-emerging llamas'
modifier = '1'
manual_expected_default_filepath = Path('/', 'tmp', 'something.json')
manual_expected_modified_filepath = Path('/', 'tmp', 'something-1.json')


@pytest.fixture(scope='function', autouse=True)
def expected_configuration_filepaths():

    # Setup
    if manual_expected_default_filepath.exists():
        manual_expected_default_filepath.unlink()
    if manual_expected_modified_filepath.exists():
        manual_expected_modified_filepath.unlink()

    yield manual_expected_default_filepath, manual_expected_modified_filepath

    # Teardown
    if manual_expected_default_filepath.exists():
        manual_expected_default_filepath.unlink()
    if manual_expected_modified_filepath.exists():
        manual_expected_modified_filepath.unlink()


class RestorableTestItem(BaseConfiguration):

    NAME = 'something'
    DEFAULT_CONFIG_ROOT = Path('/tmp')
    VERSION = 1

    def __init__(self, item: str, *args, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)

    def static_payload(self) -> dict:
        payload = dict(**super().static_payload(),
                       item=self.item)
        return payload


def test_base_configuration_defaults():
    assert BaseConfiguration.DEFAULT_CONFIG_ROOT == DEFAULT_CONFIG_ROOT
    assert BaseConfiguration.NAME == NotImplemented
    assert BaseConfiguration._CONFIG_FILE_EXTENSION == expected_extension


def test_configuration_implementation():

    # Cannot init BaseClass without subclassing
    with pytest.raises(TypeError):
        _bad_item = BaseConfiguration()

    # Subclasses must implement static_payload specification
    class BadConfigurableItem(BaseConfiguration):
        VERSION = 1
        pass

    with pytest.raises(TypeError):
        _bad_item = BadConfigurableItem()

    # Subclasses must implement _NAME
    class NoNameItem(BaseConfiguration):
        VERSION = 1
        def static_payload(self) -> dict:
            item_payload = {'key': 'value'}
            payload = {**super().static_payload(), **item_payload}
            return payload

    with pytest.raises(TypeError):
        _bad_item = NoNameItem()

    # Correct minimum viable implementation
    class BareMinimumConfigurableItem(BaseConfiguration):

        NAME = 'bare-minimum'
        VERSION = 2

        def static_payload(self) -> dict:
            item_payload = {'key': 'value'}
            payload = {**super().static_payload(), **item_payload}
            return payload

    _bare_minimum = BareMinimumConfigurableItem()


def test_configuration_creation():
    restorable_item = RestorableTestItem(item=configuration_value)
    assert restorable_item.config_root == RestorableTestItem.DEFAULT_CONFIG_ROOT
    assert restorable_item.item == configuration_value


def test_configuration_filepath_utilities():

    #
    # Class-Scoped
    #

    assert RestorableTestItem._CONFIG_FILE_EXTENSION == expected_extension

    assert RestorableTestItem.NAME == configuration_name
    expected_default_filename = f'{RestorableTestItem.NAME}.{RestorableTestItem._CONFIG_FILE_EXTENSION}'
    assert RestorableTestItem.generate_filename() == expected_default_filename

    expected_default_filepath = RestorableTestItem.DEFAULT_CONFIG_ROOT / expected_default_filename
    assert expected_default_filepath == manual_expected_default_filepath
    assert RestorableTestItem.default_filepath() == expected_default_filepath

    restorable_item = RestorableTestItem(item=configuration_value)  # <-- CREATE
    restorable_item.to_configuration_file()

    #
    # Instance-scoped
    #

    # Ensure filename and filepath construction accuracy
    expected_modified_filename = f'{RestorableTestItem.NAME}-{modifier}.{RestorableTestItem._CONFIG_FILE_EXTENSION}'
    modified_filename = restorable_item.generate_filename(modifier=modifier)
    assert modified_filename == expected_modified_filename

    expected_modified_filepath = RestorableTestItem.DEFAULT_CONFIG_ROOT / expected_modified_filename
    modified_filepath = restorable_item.generate_filepath(override=False, modifier=modifier)
    assert modified_filepath == expected_modified_filepath

    # Ensure Positive Override Control
    filepath = restorable_item.to_configuration_file(override=False, modifier=modifier)
    assert filepath == expected_modified_filepath


def test_configuration_preservation():

    # Create
    restorable_item = RestorableTestItem(item=configuration_value)

    expected_default_filename = f'{RestorableTestItem.NAME}.{RestorableTestItem._CONFIG_FILE_EXTENSION}'
    expected_default_filepath = RestorableTestItem.DEFAULT_CONFIG_ROOT / expected_default_filename

    # Serialize
    assert restorable_item.serialize()
    assert restorable_item.static_payload()

    # Write to JSON file
    filepath = restorable_item.to_configuration_file()
    assert filepath == expected_default_filepath

    # Ensure controlled failure to override
    with pytest.raises(FileExistsError):
        _filepath = restorable_item.to_configuration_file(override=False)

    # Ensure controlled override
    filepath = restorable_item.to_configuration_file(override=True)
    assert filepath == expected_default_filepath

    # Restore from JSON Configuration
    try:

        # Ensure configuration file is readable
        with open(restorable_item.filepath, 'r') as f:
            contents = f.read()

        # Ensure file contents are JSON deserializable
        deserialized_file_contents = json.loads(contents)
        del deserialized_file_contents['version']  # do not test version of config serialization here.
        deserialized_file_contents['config_root'] = Path(deserialized_file_contents['config_root'])

        deserialized_payload = RestorableTestItem.deserialize(payload=contents)
        assert deserialized_payload == deserialized_file_contents

        # Restore from JSON file
        restored_item = RestorableTestItem.from_configuration_file()
        assert restorable_item.serialize() == restored_item.serialize()
        assert restorable_item.item == configuration_value
        assert restorable_item.filepath == expected_default_filepath

    finally:
        shutil.rmtree(restorable_item.filepath, ignore_errors=True)
