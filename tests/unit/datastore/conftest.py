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

from constant_sorrow.constants import MOCK_DB
import lmdb
import pytest
import shutil
import tempfile

from nucypher.datastore import datastore


@pytest.fixture(scope='function')
def mock_or_real_datastore(request):
    if request.param:
        yield datastore.Datastore(MOCK_DB)
    else:
        temp_path = tempfile.mkdtemp()
        yield datastore.Datastore(temp_path)
        shutil.rmtree(temp_path)


@pytest.fixture(scope='function')
def mock_or_real_lmdb_env(request):
    if request.param:
        yield lmdb.open(MOCK_DB)
    else:
        temp_path = tempfile.mkdtemp()
        yield lmdb.open(temp_path)
        shutil.rmtree(temp_path)


def pytest_generate_tests(metafunc):

    if 'mock_or_real_datastore' in metafunc.fixturenames:
        values = [False, True]
        ids = ['real_datastore', 'mock_datastore']
        metafunc.parametrize('mock_or_real_datastore', values, ids=ids, indirect=True)

    if 'mock_or_real_lmdb_env' in metafunc.fixturenames:
        values = [False, True]
        ids = ['real_lmdb_env', 'mock_lmdb_env']
        metafunc.parametrize('mock_or_real_lmdb_env', values, ids=ids, indirect=True)
