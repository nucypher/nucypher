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
from threading import Lock
from typing import Optional

import maya


class Cache:
    def __init__(self):
        self.cache = {}
        self.cache_lock = Lock()

    def get(self, key):
        with self.cache_lock:
            try:
                return self.cache[key]
            except KeyError:
                return None

    def put(self, key, value):
        with self.cache_lock:
            self.cache[key] = value

    def invalidate(self, key):
        with self.cache_lock:
            if key in self.cache:
                del self.cache[key]

    def size(self):
        with self.cache_lock:
            return len(self.cache)

    def clear(self):
        with self.cache_lock:
            self.cache.clear()


class TTLCache(Cache):
    class TTLEntry:
        def __init__(self, value: object, ttl: int, last_updated: Optional[maya.MayaDT] = None):
            self.value = value
            self.expiration = (last_updated or maya.now()).add(seconds=ttl)

        def get(self):
            if not self.is_expired():
                return self.value

            return None

        def is_expired(self):
            return self.expiration < maya.now()

    def __init__(self, ttl: int):
        super().__init__()
        self.ttl = ttl

    def get_expiration(self, key):
        ttl_entry = super().get(key)
        if ttl_entry:
            return ttl_entry.expiration

        return None

    def get(self, key):
        result = None
        ttl_entry = super().get(key)
        if ttl_entry:
            result = ttl_entry.get()
            if not result:
                super().invalidate(key)

        return result

    def put(self, key, value):
        ttl_entry = self.TTLEntry(value=value, ttl=self.ttl)
        super().put(key, ttl_entry)
