import json
from io import StringIO

from typing import Union

from io import BytesIO

import nucypher


class TestRPCResponse:
    """A mock RPC response object"""

    delimiter = '\n'

    def __init__(self,
                 id: int,
                 payload: dict,
                 success: bool,
                 error: bool):

        # Initial State
        self.id = id
        self.data = payload
        self.success = success
        self.error = error

    def __bytes__(self):
        return json.dumps(self.data)

    @property
    def error_code(self):
        if self.error:
            return int(self.data['error']['code'])
        else:
            return 0

    @property
    def content(self):
        if self.success:
            return self.data['result']
        else:
            return self.data['error']

    @classmethod
    def from_string(cls, response_line: str):
        outgoing_responses = response_line.strip(cls.delimiter).split(cls.delimiter)

        responses = list()
        for response in outgoing_responses:
            # Deserialize
            response_data = json.loads(response)

            # Check for Success or Error
            error = False
            response_id_value = response_data['id']
            try:
                response_id = int(response_id_value)
            except TypeError:
                if response_id_value is not None:
                    raise
                error, response_id = True, None

            instance = cls(payload=response_data,
                           success=not error,
                           error=error,
                           id=response_id)

            responses.append(instance)

        # handle one or many requests
        final_response = responses
        if not len(responses) > 1:
            final_response = responses[0]

        return final_response


class JSONRPCTestClient:
    """A test client for character RPC control."""

    MESSAGE_ID = 0

    __preamble = json.dumps(dict(jsonrpc="2.0", version=str(nucypher.__version__)))
    __io = StringIO(initial_value=str(__preamble.encode()))
    response_sink = __io.write

    def __init__(self, rpc_controller):

        # Divert the emitter flow to the RPC pipe
        rpc_controller._internal_controller.emitter.sink = self.response_sink
        rpc_controller.emitter.sink = self.response_sink
        self._controller = rpc_controller

    def assemble_request(self, request: Union[dict, list]) -> dict:
        """Assemble a JSONRPC2.0 formatted dict for JSON use."""
        JSONRPCTestClient.MESSAGE_ID += 1
        method, params = request['method'], request['params']
        response_data = {'jsonrpc': '2.0',
                         'id': str(JSONRPCTestClient.MESSAGE_ID),
                         'method': method,
                         'params': params}

        return response_data

    def receive(self, size: int):
        current_cursor_position = self.__io.tell()
        cursor_position = current_cursor_position - size
        self.__io.seek(cursor_position)
        stdout = self.__io.read(size)
        response = TestRPCResponse.from_string(response_line=stdout)
        return response

    def send(self, request: Union[dict, list], malformed: bool = False) -> TestRPCResponse:

        # Assemble
        if malformed:
            # Allow a malformed request for testing and
            # bypass all this business below
            payload = json.dumps(request)

        else:
            # Handle single or bulk requests
            requests = request
            if isinstance(request, dict):
                requests = [request]

            payload = list()
            for r in requests:
                assembled_request = self.assemble_request(request=r)
                payload.append(assembled_request)

            if not len(payload) > 1:
                payload = payload[0]

            payload = json.dumps(payload)

        # Request
        response_size = self._controller.handle_request(control_request=payload)

        # Respond
        return self.receive(size=response_size)
