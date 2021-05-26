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

from nucypher.control.specifications.base import BaseSchema
from nucypher.control.specifications import fields as base_fields
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
    click.option(
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
            help="Total number of ursualas needed",
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
    exclude_ursulas = base_fields.List(fields.ChecksumAddress(
        required=False,
        load_only=True,
        click=click.option(
            '--exclude-ursula',
            '-e',
            help="Ursula checksum address",
            type=types.EIP55_CHECKSUM_ADDRESS, required=False)))

    include_ursulas = base_fields.List(fields.ChecksumAddress(
        required=False,
        load_only=True,
        click=click.option(
            '--include-ursula',
            '-i',
            help="Ursula checksum address",
            type=types.EIP55_CHECKSUM_ADDRESS, required=False)))

    # output
    ursulas = base_fields.List(fields.ChecksumAddress(), dump_only=True)


class AlicePublishTreasureMap(BaseSchema):
    treasure_map = character_fields.TreasureMap(
        required=True,
        load_only=True,
        click=click.option(
            '--treasure-map',
            '-t',
            help="TreasureMap",
            type=click.STRING,
            required=True))
    bob_encrypting_key = character_fields.Key(
        required=True,
        load_only=True,
        click=option_bob_encrypting_key())


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
            help="TreasureMap ID as hex",
            type=click.STRING,
            required=True))
    bob_encrypting_key = character_fields.Key(
        required=True,
        load_only=True,
        click=option_bob_encrypting_key())

    # output
    treasure_map = character_fields.TreasureMap(dump_only=True)


class BobExecWorkOrder(BaseSchema):
    ursula = fields.ChecksumAddress(
        required=True,
        load_only=True,
        click=option_ursula())
    work_order = fields.WorkOrder(
        required=True,
        load_only=True,
        click=click.option(
            '--work-order',
            '-w',
            help="Re-encryption work order",
            type=click.STRING, required=True))

    # output
    work_order_result = fields.WorkOrderResult(dump_only=True)
