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
from twisted.logger import ILogObserver
from twisted.logger import LogLevel
from twisted.python.logfile import DailyLogFile
from zope.interface import provider

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


def _get_or_create_user_log_dir():
    return pathlib.Path(USER_LOG_DIR).mkdir(parents=True, exist_ok=True)


def getJsonFileObserver(name="ursula.log.json", path=USER_LOG_DIR):  # TODO: More configurable naming here?
    _get_or_create_user_log_dir()
    logfile = DailyLogFile(name, path)
    observer = jsonFileLogObserver(outFile=logfile)
    return observer


def getTextFileObserver(name="nucypher.log", path=USER_LOG_DIR):
    _get_or_create_user_log_dir()
    logfile = DailyLogFile(name, path)
    observer = FileLogObserver(formatEvent=formatEventAsClassicLogText, outFile=logfile)
    return observer


class SimpleObserver:

    @provider(ILogObserver)
    def __call__(self, event):
        if event['log_level'] >= GlobalConsoleLogger.log_level:
            event['log_format'] = event['log_format']
            print(formatEvent(event))


class GlobalConsoleLogger:

    log_level = LogLevel.levelWithName("info")
    started = False

    @classmethod
    def set_log_level(cls, log_level_name):
        cls.log_level = LogLevel.levelWithName(log_level_name)
        if not cls.started:
            cls.start()

    @classmethod
    def start(cls):
        globalLogPublisher.addObserver(getTextFileObserver())
        cls.started = True

    @classmethod
    def start_if_not_started(cls):
        if not cls.started:
            cls.start()


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
