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
from contextlib import contextmanager
from functools import lru_cache
import pathlib

from sentry_sdk import capture_exception, add_breadcrumb
from sentry_sdk.integrations.logging import LoggingIntegration
from twisted.logger import FileLogObserver, jsonFileLogObserver, formatEvent, formatEventAsClassicLogText
from twisted.logger import ILogObserver
from twisted.logger import LogLevel
from twisted.logger import globalLogPublisher, globalLogBeginner
from twisted.python.logfile import DailyLogFile

import nucypher
from nucypher.config.constants import USER_LOG_DIR, NUCYPHER_SENTRY_ENDPOINT


def initialize_sentry(dsn: str):
    import sentry_sdk
    import logging

    # Logger blacklist
    from nucypher.blockchain.eth.clients import NuCypherGethProcess
    ignored_loggers = (NuCypherGethProcess._LOG_NAME, )

    def before_breadcrumb(crumb, hint):
        logger = crumb.get('category')
        if logger in ignored_loggers:
            return
        return crumb

    def before_send(event, hint):
        logger = event.get('logger')
        if logger in ignored_loggers:
            return
        return event

    sentry_logging = LoggingIntegration(
        level=logging.DEBUG,       # Capture debug and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )
    sentry_sdk.init(
        dsn=dsn,
        release=nucypher.__version__,
        integrations=[sentry_logging],
        before_breadcrumb=before_breadcrumb,
        before_send=before_send
    )


class GlobalLoggerSettings:

    log_level = LogLevel.levelWithName("info")

    @classmethod
    def set_log_level(cls, log_level_name):
        cls.log_level = LogLevel.levelWithName(log_level_name)

    @classmethod
    def start_console_logging(cls):
        globalLogPublisher.addObserver(console_observer)

    @classmethod
    def stop_console_logging(cls):
        globalLogPublisher.removeObserver(console_observer)

    @classmethod
    @contextmanager
    def pause_console_logging_while(cls):
        was_already_going = console_observer in globalLogPublisher._observers
        if was_already_going:
             globalLogPublisher.removeObserver(console_observer)
        yield
        if was_already_going:
            globalLogPublisher.addObserver(console_observer)

    @classmethod
    def start_text_file_logging(cls):
        globalLogPublisher.addObserver(get_text_file_observer())

    @classmethod
    def stop_text_file_logging(cls):
        globalLogPublisher.removeObserver(get_text_file_observer())

    @classmethod
    def start_json_file_logging(cls):
        globalLogPublisher.addObserver(get_json_file_observer())

    @classmethod
    def stop_json_file_logging(cls):
        globalLogPublisher.removeObserver(get_json_file_observer())

    @classmethod
    def start_sentry_logging(cls, dsn: str):
        _SentryInitGuard.init(dsn)
        globalLogPublisher.addObserver(sentry_observer)

    @classmethod
    def stop_sentry_logging(cls):
        globalLogPublisher.removeObserver(sentry_observer)


def console_observer(event):
    if event['log_level'] >= GlobalLoggerSettings.log_level:
        print(formatEvent(event))


class _SentryInitGuard:

    initialized = False
    dsn = None

    @classmethod
    def init(cls, dsn: str = NUCYPHER_SENTRY_ENDPOINT):
        if not cls.initialized:
            initialize_sentry(dsn)
        else:
            raise ValueError(f"Sentry has been already initialized with DSN {cls.dsn}")


def sentry_observer(event):
    # Handle breadcrumbs...
    if not event.get('isError') or 'failure' not in event:
        add_breadcrumb(level=event.get('log_level').name,
                       message=event.get('log_format'),
                       category=event.get('log_namespace'))
        return

    # ...Handle Failures
    f = event['failure']
    capture_exception((f.type, f.value, f.getTracebackObject()))


def _ensure_dir_exists(path):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_json_file_observer(name="nucypher.log.json", path=USER_LOG_DIR):  # TODO: More configurable naming here?
    _ensure_dir_exists(path)
    logfile = DailyLogFile(name, path)
    observer = jsonFileLogObserver(outFile=logfile)
    return observer


@lru_cache()
def get_text_file_observer(name="nucypher.log", path=USER_LOG_DIR):
    _ensure_dir_exists(path)
    logfile = DailyLogFile(name, path)
    observer = FileLogObserver(formatEvent=formatEventAsClassicLogText, outFile=logfile)
    return observer
