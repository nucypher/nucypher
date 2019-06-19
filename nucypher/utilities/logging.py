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


import datetime
import pathlib

from sentry_sdk import capture_exception, add_breadcrumb
from sentry_sdk.integrations.logging import LoggingIntegration
from twisted.logger import FileLogObserver, jsonFileLogObserver, formatEvent, formatEventAsClassicLogText
from twisted.logger import LogLevel
from twisted.python.logfile import DailyLogFile

import nucypher
from nucypher.config.constants import USER_LOG_DIR
from twisted.logger import globalLogPublisher


def initialize_sentry(dsn: str):
    import sentry_sdk
    import logging

    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.DEBUG  # Send debug logs as events
    )
    sentry_sdk.init(
        dsn=dsn,
        integrations=[sentry_logging],
        release=nucypher.__version__
    )


def _ensure_dir_exists(path):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def getJsonFileObserver(name="ursula.log.json", path=USER_LOG_DIR):  # TODO: More configurable naming here?
    _ensure_dir_exists(path)
    logfile = DailyLogFile(name, path)
    observer = jsonFileLogObserver(outFile=logfile)
    return observer


def getTextFileObserver(name="nucypher.log", path=USER_LOG_DIR):
    _ensure_dir_exists(path)
    logfile = DailyLogFile(name, path)
    observer = FileLogObserver(formatEvent=formatEventAsClassicLogText, outFile=logfile)
    return observer


def logToConsole(event):
    if event['log_level'] >= GlobalLogger.log_level:
        print(formatEvent(event))


class GlobalLogger:

    log_level = LogLevel.levelWithName("info")
    log_to_sentry = False
    log_to_file = False
    log_to_console = False

    text_file_observer = None
    json_file_observer = None

    @classmethod
    def set_log_level(cls, log_level_name):
        cls.log_level = LogLevel.levelWithName(log_level_name)

    @classmethod
    def set_log_level_from_verbosity(cls, verbose):
        if verbose >= 2:
            cls.set_log_level("debug")
        elif verbose == 1:
            cls.set_log_level("info")
        else:
            cls.set_log_level("warn")

    @classmethod
    def set_sentry_logging(cls, state: bool):
        if state and not cls.log_to_sentry:
            initialize_sentry(dsn=__sentry_endpoint)
            globalLogPublisher.addObserver(logToSentry)
            cls.log_to_sentry = True
        elif not state and cls.log_to_sentry:
            globalLogPublisher.removeObserver(logToSentry)
            cls.log_to_sentry = False

    @classmethod
    def set_file_logging(cls, state: bool):
        if state and not cls.log_to_file:
            cls.text_file_observer = getTextFileObserver()
            cls.json_file_observer = getJsonFileObserver()
            globalLogPublisher.addObserver(cls.text_file_observer)
            globalLogPublisher.addObserver(cls.json_file_observer)
            cls.log_to_file = True
        elif not state and cls.log_to_file:
            globalLogPublisher.removeObserver(cls.text_file_observer)
            globalLogPublisher.removeObserver(cls.json_file_observer)
            cls.text_file_observer = None
            cls.json_file_observer = None
            cls.log_to_file = False

    @classmethod
    def set_console_logging(cls, state: bool):
        if state and not cls.log_to_console:
            globalLogPublisher.addObserver(logToConsole)
            cls.log_to_console = True
        elif not state and cls.log_to_console:
            globalLogPublisher.removeObserver(logToConsole)
            cls.log_to_console = False


def logToSentry(event):

    # Handle Logs...
    if not event.get('isError') or 'failure' not in event:
        add_breadcrumb(level=event.get('log_level').name,
                       message=event.get('log_format'),
                       category=event.get('log_namespace'))
        return

    # ...Handle Failures
    f = event['failure']
    capture_exception((f.type, f.value, f.getTracebackObject()))
