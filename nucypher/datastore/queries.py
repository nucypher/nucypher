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

from typing import List, Type

from nucypher.datastore.base import DatastoreRecord
from nucypher.datastore.datastore import Datastore, RecordNotFound
from nucypher.datastore.models import PolicyArrangement, TreasureMap, Workorder


def find_expired_policies(ds: Datastore, now) -> List[Type['DatastoreRecord']]:
    try:
        return ds.query_by(PolicyArrangement,
                           filter_field='expiration',
                           filter_func=lambda expiration: expiration <= now,
                           writeable=True)
    except RecordNotFound:
        return []


def find_expired_treasure_maps(ds: Datastore, now) -> List[Type['DatastoreRecord']]:
    try:
        return ds.query_by(TreasureMap,
                           filter_field='expiration',
                           filter_func=lambda expiration: expiration <= now,
                           writeable=True)
    except RecordNotFound:
        return []


def find_work_orders(ds: Datastore) -> List[Type['DatastoreRecord']]:
    try:
        return ds.query_by(Workorder)
    except RecordNotFound:
        return []


def find_policy_arrangements(ds: Datastore, writeable=False) -> List[Type['DatastoreRecord']]:
    try:
        return ds.query_by(PolicyArrangement, writeable=writeable)
    except RecordNotFound:
        return []
