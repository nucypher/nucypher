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
import pytest
import json

import nucypher
from nucypher.cli.deploy import deploy
from nucypher.cli.main import nucypher_cli

from nucypher.characters.control.specifications import CharacterSpecification


def test_echo_options(click_runner):

    for character_name in ['alice', 'bob', 'enrico']:
        all_specs = {spec._name: spec for spec in CharacterSpecification.__subclasses__()}
        specification = all_specs[character_name]()

        result = dict()
        for interface, io in specification._specifications.items():
            args = (
                character_name,
                interface,
                '--options',
                '--json-ipc',
            )
            result = click_runner.invoke(
                nucypher_cli, args, catch_exceptions=False
            )
            result_json = json.loads(result.stdout)
            assert list(result_json['result'].keys())== list(io['input'])
