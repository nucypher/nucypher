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
from marshmallow import validates_schema
from marshmallow import fields as marshmallow_fields

from nucypher.control.specifications.base import BaseSchema
from nucypher.control.specifications import fields as base_fields
from nucypher.control.specifications.exceptions import InvalidArgumentCombo
from nucypher.utilities.porter.control.specifications import fields
from nucypher.characters.control.specifications import fields as character_fields
from nucypher.cli import types


def option_ursula():
    return click.option(
        '--ursula',
        '-u',
        help="Ursula checksum address",
        type=types.EIP55_CHECKSUM_ADDRESS,
        required=True)


def option_bob_encrypting_key():
    return click.option(
        '--bob-encrypting-key',
        '-bek',
        help="Bob's encrypting key as a hexadecimal string",
        type=click.STRING,
        required=True)


#
# Alice Endpoints
#
class AliceGetUrsulas(BaseSchema):
    quantity = base_fields.PositiveInteger(
        required=True,
        load_only=True,
        click=click.option(
            '--quantity',
            '-n',
            help="Total number of Ursulas needed",
            type=click.INT, required=True))
    duration_periods = base_fields.PositiveInteger(
        required=True,
        load_only=True,
        click=click.option(
            '--periods',
            '-p',
            help="Required duration of service for Ursulas",
            type=click.INT, required=True))

    # optional
    exclude_ursulas = base_fields.StringList(
        fields.UrsulaChecksumAddress(),
        click=click.option(
            '--exclude-ursula',
            '-e',
            help="Ursula checksum address to exclude from sample",
            multiple=True,
            type=types.EIP55_CHECKSUM_ADDRESS,
            required=False,
            default=[]),
        required=False,
        load_only=True)

    include_ursulas = base_fields.StringList(
        fields.UrsulaChecksumAddress(),
        click=click.option(
            '--include-ursula',
            '-i',
            help="Ursula checksum address to include in sample",
            multiple=True,
            type=types.EIP55_CHECKSUM_ADDRESS,
            required=False,
            default=[]),
        required=False,
        load_only=True)

    # output
    ursulas = marshmallow_fields.List(marshmallow_fields.Nested(fields.UrsulaInfoSchema), dump_only=True)
    
    @validates_schema
    def check_valid_quantity_and_include_ursulas(self, data, **kwargs):
        # TODO does this make sense - perhaps having extra ursulas could be a good thing if some are down or can't
        #  be contacted at that time
        ursulas_to_include = data.get('include_ursulas')
        if ursulas_to_include and len(ursulas_to_include) > data['quantity']:
            raise InvalidArgumentCombo(f"Ursulas to include is greater than quantity requested")

    @validates_schema
    def check_include_and_exclude_are_mutually_exclusive(self, data, **kwargs):
        ursulas_to_include = data.get('include_ursulas') or []
        ursulas_to_exclude = data.get('exclude_ursulas') or []
        common_ursulas = set(ursulas_to_include).intersection(ursulas_to_exclude)
        if len(common_ursulas) > 0:
            raise InvalidArgumentCombo(f"Ursulas to include and exclude are not mutually exclusive; "
                                       f"common entries {common_ursulas}")


class AlicePublishTreasureMap(BaseSchema):
    treasure_map = character_fields.TreasureMap(
        required=True,
        load_only=True,
        click=click.option(
            '--treasure-map',
            '-t',
            help="Treasure Map to publish",
            type=click.STRING,
            required=True))
    bob_encrypting_key = character_fields.Key(
        required=True,
        load_only=True,
        click=option_bob_encrypting_key())

    # output
    published = marshmallow_fields.Bool(dump_only=True)


class AliceRevoke(BaseSchema):
    pass  # TODO need to understand revoke process better


#
# Bob Endpoints
#
class BobGetTreasureMap(BaseSchema):
    treasure_map_id = fields.TreasureMapID(
        required=True,
        load_only=True,
        click=click.option(
            '--treasure-map-id',
            '-tid',
            help="Treasure Map ID as hex",
            type=click.STRING,
            required=True))
    bob_encrypting_key = character_fields.Key(
        required=True,
        load_only=True,
        click=option_bob_encrypting_key())

    # output
    # treasure map only used for serialization so no need to provide federated/non-federated context
    treasure_map = character_fields.TreasureMap(dump_only=True)


class BobExecWorkOrder(BaseSchema):
    ursula = fields.UrsulaChecksumAddress(
        required=True,
        load_only=True,
        click=option_ursula())
    work_order_payload = fields.WorkOrder(
        required=True,
        load_only=True,
        click=click.option(
            '--work-order',
            '-w',
            help="Re-encryption work order",
            type=click.STRING, required=True))

    # output
    work_order_result = fields.WorkOrderResult(dump_only=True)
