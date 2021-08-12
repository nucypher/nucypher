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

from bisect import bisect_left
from contextlib import contextmanager
from pathlib import Path

import lmdb
from threading import Lock

from constant_sorrow.constants import MOCK_DB


def mock_lmdb_open(db_path: Path, map_size=10485760):
    if db_path == MOCK_DB:
        return MockEnvironment()
    else:
        return lmdb.Environment(str(db_path), map_size=map_size)


class MockEnvironment:

    def __init__(self):
        self._storage = {}
        self._lock = Lock()

    @contextmanager
    def begin(self, write=False):
        with self._lock:
            with MockTransaction(self, write=write) as tx:
                yield tx


class MockTransaction:

    def __init__(self, env, write=False):
        self._env = env
        self._storage = dict(env._storage)
        self._write = write
        self._invalid = False

    def __enter__(self):
        if self._invalid:
            raise lmdb.Error()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.abort()
        else:
            self.commit()

    def put(self, key, value, overwrite=True):
        if self._invalid:
            raise lmdb.Error()
        assert self._write
        if not overwrite and key in self._storage:
            return False
        self._storage[key] = value
        return True

    def get(self, key, default=None):
        if self._invalid:
            raise lmdb.Error()
        return self._storage.get(key, default)

    def delete(self, key):
        if self._invalid:
            raise lmdb.Error()
        assert self._write
        if key in self._storage:
            del self._storage[key]
            return True
        else:
            return False

    def commit(self):
        if self._invalid:
            raise lmdb.Error()
        self._invalidate()
        self._env._storage = self._storage

    def abort(self):
        self._invalidate()
        self._storage = self._env._storage

    def _invalidate(self):
        self._invalid = True

    def cursor(self):
        return MockCursor(self)


class MockCursor:

    def __init__(self, tx):
        self._tx = tx
        # TODO: assuming here that the keys are not changed while the cursor exists.
        # Any way to enforce it?
        self._keys = list(sorted(tx._storage))
        self._pos = None

    def set_range(self, key):
        pos = bisect_left(self._keys, key)
        if pos == len(self._keys):
            self._pos = None
            return False
        else:
            self._pos = pos
            return True

    def key(self):
        return self._keys[self._pos]

    def iternext(self, keys=True, values=True):
        return iter(self._keys[self._pos:])
