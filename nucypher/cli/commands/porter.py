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

from nucypher.utilities.porter.control.interfaces import PorterInterface


@click.group()
def porter():
    """
    Porter management commands. Porter is the conduit between web apps and the nucypher network, that performs actions
    on behalf of Alice and Bob.
    """


@porter.command()
@PorterInterface.connect_cli('get_ursulas')
def get_ursulas(porter_uri, quantity, duration_periods, exclude_ursulas, include_ursulas):
    """Sample ursulas on behalf of Alice."""
    pass


@porter.command()
@PorterInterface.connect_cli('publish_treasure_map')
def publish_treasure_map(porter_uri, treasure_map, bob_encrypting_key):
    """Publish a treasure map on behalf of Alice."""
    pass


@porter.command()
@PorterInterface.connect_cli('revoke')
def revoke(porter_uri):
    """Off-chain revoke of a policy on behalf of Alice."""
    pass


@porter.command()
@PorterInterface.connect_cli('get_treasure_map')
def get_treasure_map(porter_uri, treasure_map_id, bob_encrypting_key):
    """Retrieve a treasure map on behalf of Bob."""
    pass


@porter.command()
@PorterInterface.connect_cli('exec_work_order')
def exec_work_order(porter_uri, ursula, work_order):
    """Execute a PRE work order on behalf of Bob."""
    pass


@porter.command()
def run(teacher_uri, network, provider_uri, http_port, dry_run, eager):
    """Start Porter's Web controller."""
    pass
