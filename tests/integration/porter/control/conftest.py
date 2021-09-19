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


#
# Web
#
@pytest.fixture(scope='module')
def federated_porter_web_controller(federated_porter):
    web_controller = federated_porter.make_web_controller(crash_on_error=False)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def federated_porter_basic_auth_web_controller(federated_porter, basic_auth_file):
    web_controller = federated_porter.make_web_controller(crash_on_error=False, htpasswd_filepath=basic_auth_file)
    yield web_controller.test_client()


#
# RPC
#
@pytest.fixture(scope='module')
def federated_porter_rpc_controller(federated_porter):
    rpc_controller = federated_porter.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()
