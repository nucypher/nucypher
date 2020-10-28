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

from io import StringIO
from json.encoder import py_encode_basestring_ascii

import pytest
from twisted.logger import Logger as TwistedLogger, formatEvent, jsonFileLogObserver

from nucypher.utilities.logging import Logger


def naive_print_observer(event):
    print(formatEvent(event), end="")


def get_json_observer_for_file(logfile):
    def json_observer(event):
        observer = jsonFileLogObserver(outFile=logfile)
        return observer(event)
    return json_observer


ordinary_string = "And you're boring, and you're totally ordinary, and you know it"
quirky_but_ok_strings = (
    "{{}}", "{{hola}}", "{{{{}}}}", "foo{{}}",
)
normal_strings = (ordinary_string, *quirky_but_ok_strings)

freaky_format_strings = (  # Including the expected exception and error message
    ("{", ValueError, "Single '{' encountered in format string"),
    ("}", ValueError, "Single '}' encountered in format string"),
    ("foo}", ValueError, "Single '}' encountered in format string"),
    ("bar{", ValueError, "Single '{' encountered in format string"),
    ("}{", ValueError, "Single '}' encountered in format string"),
    (f"{b'{'}", ValueError, "expected '}' before end of string"),
    (f"{b'}'}", ValueError, "Single '}' encountered in format string"),
    ("{}", KeyError, ""),
    ("{{{}}}", KeyError, ""),
    ("{{{{{}}}}}", KeyError, ""),
    ("{bananas}", KeyError, "bananas"),
    (str({'bananas': '🍌🍌🍌'}), KeyError, "bananas"),
)


def test_twisted_logger_doesnt_like_curly_braces(capsys):
    twisted_logger = TwistedLogger('twisted', observer=naive_print_observer)

    # Normal strings are logged normally
    for string in normal_strings:
        twisted_logger.info(string)
        captured = capsys.readouterr()
        assert string.format() == captured.out

    # But curly braces are not
    for string, exception, exception_message in freaky_format_strings:
        twisted_logger.info(string)
        captured = capsys.readouterr()
        assert string != captured.out
        assert "Unable to format event" in captured.out


def test_twisted_json_logger_doesnt_like_curly_braces():
    twisted_logger = TwistedLogger('twisted-json')

    # Normal strings are logged normally
    for string in normal_strings:
        file = StringIO()
        twisted_logger.observer = get_json_observer_for_file(file)
        twisted_logger.info(string)
        logged_event = file.getvalue()
        assert '"log_level": {"name": "info"' in logged_event
        assert f'"log_format": "{string}"' in logged_event

    # But curly braces are not
    for string, exception, exception_message in freaky_format_strings:
        file = StringIO()
        twisted_logger.observer = get_json_observer_for_file(file)
        with pytest.raises(exception, match=exception_message):
            twisted_logger.info(string)


def test_but_nucypher_logger_is_cool_with_that(capsys):
    nucypher_logger = Logger('nucypher-logger', observer=naive_print_observer)

    # Normal strings are logged normally
    for string in normal_strings:
        nucypher_logger.info(string)
        captured = capsys.readouterr()
        assert string.format() == captured.out

    # And curly braces too!
    for string, exception, exception_message in freaky_format_strings:
        nucypher_logger.info(string)
        captured = capsys.readouterr()
        assert "Unable to format event" not in captured.out
        assert string == captured.out


def test_even_nucypher_json_logger_is_cool():
    nucypher_logger = Logger('nucypher-logger-json')

    # Normal strings are logged normally
    for string in normal_strings:
        file = StringIO()
        nucypher_logger.observer = get_json_observer_for_file(file)
        nucypher_logger.info(string)
        logged_event = file.getvalue()
        assert '"log_level": {"name": "info"' in logged_event
        assert f'"log_format": "{string}"' in logged_event

    # And curly braces too!
    for string, _exception, _exception_message in freaky_format_strings:
        file = StringIO()
        nucypher_logger.observer = get_json_observer_for_file(file)
        nucypher_logger.info(string)
        logged_event = file.getvalue()
        assert '"log_level": {"name": "info"' in logged_event
        ascii_string = py_encode_basestring_ascii(string)[1:-1]
        assert f'"log_format": "{Logger.escape_format_string(ascii_string)}"' in logged_event
