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
import json
import sys

from flask import Response, request

from nucypher.control.controllers import WebController
from nucypher.utilities.concurrency import WorkerPoolException
from nucypher.utilities.porter.control.interfaces import PorterInterface


def test_web_controller_handling_worker_pool_exception(mocker):
    interface_impl = mocker.Mock()
    num_failures = 3
    message_prefix = "Execution failed because test designed that way"

    def get_ursulas_method(*args, **kwargs):
        failures = {}
        for i in range(num_failures):
            try:
                raise ValueError(f'error_{i}')
            except BaseException as e:
                failures[f"value_{i}"] = sys.exc_info()

        raise WorkerPoolException(message_prefix=message_prefix, failures=failures)

    interface_impl.get_ursulas.side_effect = get_ursulas_method
    controller = WebController(app_name="web_controller_app_test",
                               crash_on_error=False,
                               # too lazy to create test schema - use existing one
                               interface=PorterInterface(porter=interface_impl))
    control_transport = controller.make_control_transport()

    @control_transport.route('/get_ursulas', methods=['GET'])
    def get_ursulas() -> Response:
        """Porter control endpoint for sampling Ursulas on behalf of Alice."""
        response = controller(method_name='get_ursulas', control_request=request)
        return response

    client = controller.test_client()

    get_ursulas_params = {
        'quantity': 5,
    }
    response = client.get('/get_ursulas', data=json.dumps(get_ursulas_params))

    assert response.status_code == 404
    assert response.content_type == 'application/json'
    response_data = json.loads(response.data)

    assert message_prefix in response_data['result']['failure_message']
    response_failures = response_data['result']['failures']
    assert len(response_failures) == 3

    values = [f"value_{i}" for i in range(num_failures)]
    errors = [f"error_{i}" for i in range(num_failures)]
    for failure in response_failures:
        assert failure['value'] in values
        assert failure['error'] in errors

        # remove checked entry
        values.remove(failure['value'])
        errors.remove(failure['error'])
