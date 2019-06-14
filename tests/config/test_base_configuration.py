import json
import os
import shutil

import pytest

from nucypher.config.base import BaseConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT

#
# Local Test Constants
#

configuration_name = 'something'
expected_extension = 'json'
configuration_value = 're-emerging llamas'
modifier = '1'
manual_expected_default_filepath = os.path.join('/', 'tmp', 'something.json')
manual_expected_modified_filepath = os.path.join('/', 'tmp', 'something-1.json')


@pytest.fixture(scope='function', autouse=True)
def expected_configuration_filepaths():

    # Setup
    if os.path.exists(manual_expected_default_filepath):
        os.remove(manual_expected_default_filepath)
    if os.path.exists(manual_expected_modified_filepath):
        os.remove(manual_expected_modified_filepath)

    yield manual_expected_default_filepath, manual_expected_modified_filepath

    # Teardown
    if os.path.exists(manual_expected_default_filepath):
        os.remove(manual_expected_default_filepath)
    if os.path.exists(manual_expected_modified_filepath):
        os.remove(manual_expected_modified_filepath)


class RestorableTestItem(BaseConfiguration):

    _NAME = 'something'
    DEFAULT_CONFIG_ROOT = '/tmp'

    def __init__(self, item: str, *args, **kwargs):
        self.item = item
        super().__init__(*args, **kwargs)

    def static_payload(self) -> dict:
        payload = dict(**super().static_payload(),
                       item=self.item)
        return payload


def test_base_configuration_defaults():
    assert BaseConfiguration.DEFAULT_CONFIG_ROOT == DEFAULT_CONFIG_ROOT
    assert BaseConfiguration._NAME == NotImplemented
    assert BaseConfiguration._CONFIG_FILE_EXTENSION == expected_extension


def test_configuration_implementation():

    # Cannot init BaseClass without subclassing
    with pytest.raises(TypeError):
        _bad_item = BaseConfiguration()

    # Subclasses must implement static_payload specification
    class BadConfigurableItem(BaseConfiguration):
        pass

    with pytest.raises(TypeError):
        _bad_item = BadConfigurableItem()

    # Subclasses must implement _NAME
    class NoNameItem(BaseConfiguration):
        def static_payload(self) -> dict:
            item_payload = {'key': 'value'}
            payload = {**super().static_payload(), **item_payload}
            return payload

    with pytest.raises(TypeError):
        _bad_item = NoNameItem()

    # Correct minimum viable implementation
    class BareMinimumConfigurableItem(BaseConfiguration):

        _NAME = 'bare-minimum'

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

    assert RestorableTestItem._NAME == configuration_name
    expected_default_filename = f'{RestorableTestItem._NAME}.{RestorableTestItem._CONFIG_FILE_EXTENSION}'
    assert RestorableTestItem.generate_filename() == expected_default_filename

    expected_default_filepath = os.path.join(RestorableTestItem.DEFAULT_CONFIG_ROOT, expected_default_filename)
    assert expected_default_filepath == manual_expected_default_filepath
    assert RestorableTestItem.default_filepath() == expected_default_filepath

    restorable_item = RestorableTestItem(item=configuration_value)  # <-- CREATE
    restorable_item.to_configuration_file()

    #
    # Instance-scoped
    #

    # Ensure filename and filepath construction accuracy
    expected_modified_filename = f'{RestorableTestItem._NAME}-{modifier}.{RestorableTestItem._CONFIG_FILE_EXTENSION}'
    modified_filename = restorable_item.generate_filename(modifier=modifier)
    assert modified_filename == expected_modified_filename

    expected_modified_filepath = os.path.join(RestorableTestItem.DEFAULT_CONFIG_ROOT, expected_modified_filename)
    modified_filepath = restorable_item.generate_filepath(override=False, modifier=modifier)
    assert modified_filepath == expected_modified_filepath

    # Ensure Positive Override Control
    filepath = restorable_item.to_configuration_file(override=False, modifier=modifier)
    assert filepath == expected_modified_filepath


def test_configuration_preservation():

    # Create
    restorable_item = RestorableTestItem(item=configuration_value)

    expected_default_filename = f'{RestorableTestItem._NAME}.{RestorableTestItem._CONFIG_FILE_EXTENSION}'
    expected_default_filepath = os.path.join(RestorableTestItem.DEFAULT_CONFIG_ROOT, expected_default_filename)

    # Serialize
    serialized_item = restorable_item.serialize()
    serialized_payload = json.dumps(restorable_item.static_payload(), indent=4)
    assert serialized_item == serialized_payload

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

        # Ensure raw configuration file contents are accurate
        assert contents == serialized_payload

        # Ensure file contents are JSON deserializable
        deserialized_file_contents = json.loads(contents)
        deserialized_payload = RestorableTestItem.deserialize(payload=contents)
        assert deserialized_payload == deserialized_file_contents

        # Restore from JSON file
        restored_item = RestorableTestItem.from_configuration_file()
        assert restorable_item == restored_item
        assert restorable_item.item == configuration_value
        assert restorable_item.filepath == expected_default_filepath

    finally:
        shutil.rmtree(restorable_item.filepath, ignore_errors=True)

