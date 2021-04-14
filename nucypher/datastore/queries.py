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
import functools
from typing import List, Type

from nucypher.datastore.base import DatastoreRecord
from nucypher.datastore.datastore import Datastore, RecordNotFound
from nucypher.datastore.models import PolicyArrangement, TreasureMap, Workorder


def fetch(func):
    """Used to fetch lazy results. Breaks writeable records."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            with func(*args, **kwargs) as results:
                return results
        except RecordNotFound:
            return []

    return wrapper


def find_expired_policies(ds: Datastore, now) -> List[Type['DatastoreRecord']]:
    return ds.query_by(PolicyArrangement,
                       filter_field='expiration',
                       filter_func=lambda expiration: expiration <= now,
                       writeable=True)


def find_expired_treasure_maps(ds: Datastore, now) -> List[Type['DatastoreRecord']]:
    return ds.query_by(TreasureMap,
                       filter_field='expiration',
                       filter_func=lambda expiration: expiration <= now,
                       writeable=True)


@fetch
def fetch_work_orders(ds: Datastore) -> List[Type['DatastoreRecord']]:
    return ds.query_by(Workorder)


def find_policy_arrangements(ds: Datastore) -> List[Type['DatastoreRecord']]:
    return ds.query_by(PolicyArrangement, writeable=True)


@fetch
def fetch_policy_arrangements(ds: Datastore) -> List[Type['DatastoreRecord']]:
    return ds.query_by(PolicyArrangement)
