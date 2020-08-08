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

from twisted.logger import Logger as TwistedLogger, formatEvent

from nucypher.utilities.logging import Logger


def naive_print_observer(event):
    print(formatEvent(event), end="")


ordinary_string = "And you're boring, and you're totally ordinary, and you know it"
quirky_but_ok_strings = (
    "{{}}", "{{hola}}", "{{{{}}}}"
)
normal_strings = (ordinary_string, *quirky_but_ok_strings)

freak_format_strings = (
    "{}", "{", "}", "}{", "{{{}}}", "{{{{{}}}}}", "{bananas}", str({'bananas': '🍌🍌🍌'})
)


def test_twisted_logger_doesnt_like_curly_braces(capsys):
    twisted_logger = TwistedLogger('twisted', observer=naive_print_observer)

    # Normal strings are logged normally
    for string in normal_strings:
        twisted_logger.info(string)
        captured = capsys.readouterr()
        assert string.format() == captured.out

    # But curly braces are not
    for string in freak_format_strings:
        twisted_logger.info(string)
        captured = capsys.readouterr()
        assert string != captured.out
        assert "Unable to format event" in captured.out


def test_but_nucypher_logger_is_cool_with_that(capsys):
    nucypher_logger = Logger('twisted', observer=naive_print_observer)

    # Normal strings are logged normally
    for string in normal_strings:
        nucypher_logger.info(string)
        captured = capsys.readouterr()
        assert string.format() == captured.out

    # And curly braces too!
    for string in freak_format_strings:
        nucypher_logger.info(string)
        captured = capsys.readouterr()
        assert "Unable to format event" not in captured.out
        assert string == captured.out
