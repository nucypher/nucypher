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


import inspect
import json
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Optional

import maya
from flask import Flask, Response
from hendrix.deploy.base import HendrixDeploy
from hendrix.deploy.tls import HendrixDeployTLS
from twisted.internet import reactor, stdio

from nucypher.cli.processes import JSONRPCLineReceiver
from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nucypher.control.emitters import StdoutEmitter, JSONRPCStdoutEmitter, WebEmitter
from nucypher.control.interfaces import ControlInterface
from nucypher.control.specifications.exceptions import SpecificationError
from nucypher.exceptions import DevelopmentInstallationRequired
from nucypher.network.resources import get_static_resources
from nucypher.utilities.logging import Logger, GlobalLoggerSettings


class ControllerBase(ABC):
    """
    A transactional interface for a human to interact with.
    """
    _emitter_class = NotImplemented

    def __init__(self, interface: ControlInterface):
        # Control Emitter
        self.emitter = self._emitter_class()

        # Interface
        self.interface = interface

    def _perform_action(self, action: str, request: Optional[dict] = None) -> dict:
        """
        This method is where input validation and method invocation
        happens for all interface actions.
        """
        request = request or {}  # for requests with no input params request can be ''
        method = getattr(self.interface, action, None)
        serializer = method._schema
        params = serializer.load(request) # input validation will occur here.
        response = method(**params)  # < ---- INLET

        response_data = serializer.dump(response)
        return response_data


class InterfaceControlServer(ControllerBase):
    _emitter_class = StdoutEmitter
    _crash_on_error_default = False

    def __init__(self,
                 app_name: str,
                 crash_on_error: bool = _crash_on_error_default,
                 *args,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self.app_name = app_name

        # Configuration
        self.crash_on_error = crash_on_error

        def set_method(name):
            def wrapper(request=None, **kwargs):
                request = request or kwargs
                return self.handle_request(name, request)

            setattr(self, name, wrapper)

        for method_name in self._get_interfaces().keys():
            set_method(method_name)
            set_method(method_name)

        self.log = Logger(app_name)

    def _get_interfaces(self):
        return {
            name: method for name, method in
            inspect.getmembers(
                self.interface,
                predicate=inspect.ismethod)
            if hasattr(method, '_schema')
        }

    @abstractmethod
    def make_control_transport(self):
        return NotImplemented

    @abstractmethod
    def handle_request(self, method_name, control_request):
        return NotImplemented

    @abstractmethod
    def test_client(self):
        return NotImplemented


class CLIController(InterfaceControlServer):

    _emitter_class = StdoutEmitter

    def make_control_transport(self):
        return

    def test_client(self):
        return

    def handle_request(self, method_name, request) -> dict:
        response = self._perform_action(action=method_name, request=request)
        if GlobalLoggerSettings._json_ipc:
            # support for --json-ipc flag, for JSON *responses* from CLI commands-as-requests.
            start = maya.now()
            self.emitter.ipc(response=response, request_id=start.epoch, duration=maya.now() - start)
        else:
            self.emitter.pretty(response)
        return response


class JSONRPCController(InterfaceControlServer):

    _emitter_class = JSONRPCStdoutEmitter

    def start(self):
        _transport = self.make_control_transport()
        reactor.run()  # < ------ Blocking Call (Reactor)

    def test_client(self):
        try:
            from tests.utils.controllers import JSONRPCTestClient
        except ImportError:
            raise DevelopmentInstallationRequired(importable_name='tests.utils.controllers.JSONRPCTestClient')

        test_client = JSONRPCTestClient(rpc_controller=self)
        return test_client

    def make_control_transport(self):
        transport = stdio.StandardIO(JSONRPCLineReceiver(rpc_controller=self))
        return transport

    def handle_procedure_call(self, control_request) -> int:

        # Validate request and read request metadata
        jsonrpc2 = control_request['jsonrpc']
        if jsonrpc2 != '2.0':
            raise self.emitter.InvalidRequest

        request_id = control_request['id']

        # Read the interface's signature metadata
        method_name = control_request['method']
        method_params = control_request.get('params', dict())  # optional
        if method_name not in self._get_interfaces():
            raise self.emitter.MethodNotFound(f'No method called {method_name}')

        return self.call_interface(method_name=method_name,
                                   request=method_params,
                                   request_id=request_id)

    def handle_message(self, message: dict, *args, **kwargs) -> int:
        """Handle single JSON RPC message"""

        try:
            _request_id = message['id']

        except KeyError:  # Notification
            raise self.emitter.InvalidRequest('No request id')
        except TypeError:
            raise self.emitter.InvalidRequest(f'Request object not valid: {type(message)}')
        else:             # RPC
            return self.handle_procedure_call(control_request=message)

    def handle_batch(self, control_requests: list) -> int:

        if not control_requests:
            e = self.emitter.InvalidRequest()
            return self.emitter.error(e)

        batch_size = 0
        for request in control_requests:  # TODO: parallelism
            response_size = self.handle_message(message=request)
            batch_size += response_size
        return batch_size

    def handle_request(self, control_request: bytes, *args, **kwargs) -> int:

        try:
            control_request = json.loads(control_request)
        except JSONDecodeError:
            e = self.emitter.ParseError()
            return self.emitter.error(e)

        # Handle batch of messages
        if isinstance(control_request, list):
            return self.handle_batch(control_requests=control_request)

        # Handle single message
        try:
            return self.handle_message(message=control_request, *args, **kwargs)

        except self.emitter.JSONRPCError as e:
            return self.emitter.error(e)

        except Exception as e:
            if self.crash_on_error:
                raise
            return self.emitter.error(e)

    def call_interface(self, method_name, request, request_id: int = None):
        received = maya.now()
        internal_request_id = received.epoch
        if request_id is None:
            request_id = internal_request_id
        response = self._perform_action(action=method_name, request=request)
        responded = maya.now()
        duration = responded - received
        return self.emitter.ipc(response=response, request_id=request_id, duration=duration)


class WebController(InterfaceControlServer):
    """
    A wrapper around a JSON control interface that
    handles web requests to exert control over an implemented interface.
    """

    _emitter_class = WebEmitter
    _crash_on_error_default = False

    _captured_status_codes = {200: 'OK',
                              400: 'BAD REQUEST',
                              500: 'INTERNAL SERVER ERROR'}

    def test_client(self):
        test_client = self._transport.test_client()

        # ease your mind
        self._transport.config.update(TESTING=self.crash_on_error, PROPOGATE_EXCEPTION=self.crash_on_error)

        return test_client

    def make_control_transport(self):
        self._transport = Flask(self.app_name)
        self._transport.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_CONTENT_LENGTH

        # Return FlaskApp decorator
        return self._transport

    def start(self,
              port: int,
              tls_key_filepath: str = None,
              tls_certificate_filepath: str = None,
              dry_run: bool = False):
        if dry_run:
            return

        if tls_key_filepath and tls_certificate_filepath:
            self.log.info("Starting HTTPS Control...")
            # HTTPS endpoint
            hx_deployer = HendrixDeployTLS(action="start",
                                           key=tls_key_filepath,
                                           cert=tls_certificate_filepath,
                                           options={
                                               "wsgi": self._transport,
                                               "https_port": port,
                                               "resources": get_static_resources()
                                           })
        else:
            # HTTP endpoint
            # TODO #845: Make non-blocking web control startup
            self.log.info("Starting HTTP Control...")
            hx_deployer = HendrixDeploy(action="start",
                                        options={
                                            "wsgi": self._transport,
                                            "http_port": port,
                                            "resources": get_static_resources()
                                        })

        hx_deployer.run()  # <--- Blocking Call to Reactor

    def __call__(self, *args, **kwargs):
        return self.handle_request(*args, **kwargs)

    def handle_request(self, method_name, control_request, *args, **kwargs) -> Response:

        _400_exceptions = (SpecificationError,
                           TypeError,
                           JSONDecodeError,
                           self.emitter.MethodNotFound)

        try:
            request_data = control_request.data
            request_body = json.loads(request_data) if request_data else dict()

            # handle query string parameters
            if hasattr(control_request, 'args'):
                request_body.update(control_request.args)

            request_body.update(kwargs)

            if method_name not in self._get_interfaces():
                raise self.emitter.MethodNotFound(f'No method called {method_name}')

            response = self._perform_action(action=method_name, request=request_body)

        #
        # Client Errors
        #
        except _400_exceptions as e:
            __exception_code = 400
            return self.emitter.exception(
                e=e,
                log_level='debug',
                response_code=__exception_code,
                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Server Errors
        #
        except SpecificationError as e:
            __exception_code = 500
            if self.crash_on_error:
                raise
            return self.emitter.exception(
                e=e,
                log_level='critical',
                response_code=__exception_code,
                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Unhandled Server Errors
        #
        except Exception as e:
            __exception_code = 500
            if self.crash_on_error:
                raise
            return self.emitter.exception(
                e=e,
                log_level='debug',
                response_code=__exception_code,
                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Send to WebEmitter
        #
        else:
            self.log.debug(f"{method_name} [200 - OK]")
            return self.emitter.respond(response=response)
