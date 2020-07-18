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

from nucypher.cli.config import group_general_config


@click.group()
def dao():
    """Participate in the NuCypher DAO"""


@dao.command()
@group_general_config
def inspect(general_config):
    """Show current status of the NuCypher DAO"""


@dao.command()
@group_general_config
def propose(general_config):
    """Make a proposal for the NuCypher DAO"""


@dao.command()
@group_general_config
def validate(general_config):
    """Validate an existing proposal"""
