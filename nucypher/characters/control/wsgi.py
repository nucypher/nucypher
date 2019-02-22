from constant_sorrow.constants import NO_WSGI_APP
from flask import Flask, Response


class WSGIController:

    _crash_on_error_default = False

    def __init__(self,
                 app_name: str,
                 start_learning: bool = True,
                 quiet: bool = False,
                 crash_on_error: bool = _crash_on_error_default,
                 *args, **kwargs):

        self.app_name = app_name
        self.start_learning = start_learning
        self.quiet = quiet
        self.crash_on_error = crash_on_error
        self._control_protocol = self._default_controller_class(self)
        self._wsgi_app = NO_WSGI_APP
        self._captured_status_codes = NO_WSGI_APP
        super().__init__(*args, **kwargs)

    def make_wsgi_app(drone_character):

        # Protocol and Flask App
        drone_character._control_protocol = drone_character._default_controller_class(drone_character)
        drone_character._control_protocol.as_bytes = True

        drone_character._wsgi_app = Flask(drone_character.app_name)
        done_control = drone_character._wsgi_app

        # Startup Node Discovery Services "Learning Loop"
        drone_character.start_learning_loop(now=drone_character.start_learning)

        drone_character._captured_status_codes = {200: 'OK',
                                                  400: 'BAD REQUEST',
                                                  500: 'INTERNAL SERVER ERROR'}

        return done_control

    def __handle_exception(drone_character, e, log_level: str = 'info', response_code: int = 500):
        message = f"{drone_character} [{str(response_code)} - {drone_character._captured_status_codes[response_code]}] | ERROR: {str(e)}"
        if not drone_character.quiet:
            logger = getattr(drone_character.log, log_level)
            logger(message)
        if drone_character.crash_on_error:
            raise e
        return Response(str(e), status=response_code)

    def _handle_request(drone_character, interface, control_request, *args, **kwargs) -> Response:

        _400_exceptions = (drone_character.control.MissingField,
                           drone_character.control.InvalidInputField,
                           drone_character.control.SerializerError)
        try:
            response = interface(request=control_request.data, *args, **kwargs)

        except _400_exceptions as e:
            return drone_character.__handle_exception(e=e, log_level='debug', response_code=400)

        except drone_character.control.SpecificationError as e:
            return drone_character.__handle_exception(e=e, log_level='critical', response_code=500)

        except Exception as e:
            raise
            # return drone_character.__handle_exception(e=e, log_level='debug', response_code=500)

        else:
            if not drone_character.quiet:
                drone_character.log.debug(f"{drone_character} [200 - OK] | {interface.__name__}")
            return Response(response, status=200)
