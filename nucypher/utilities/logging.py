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


import pathlib
from contextlib import contextmanager
from twisted.logger import (
    FileLogObserver,
    formatEvent,
    formatEventAsClassicLogText,
    globalLogPublisher,
    jsonFileLogObserver,
    LogLevel,
)
from twisted.logger import Logger as TwistedLogger
from twisted.python.logfile import LogFile

import nucypher
from nucypher.config.constants import (
    DEFAULT_JSON_LOG_FILENAME,
    DEFAULT_LOG_FILENAME,
    NUCYPHER_SENTRY_ENDPOINT,
    USER_LOG_DIR,
)

ONE_MEGABYTE = 1_048_576
MAXIMUM_LOG_SIZE = ONE_MEGABYTE * 10
MAX_LOG_FILES = 10


def initialize_sentry(dsn: str):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        raise ImportError('Sentry SDK is not installed. Please install it and try again.')

    import logging

    # Logger ignore list
    ignored_loggers = ()

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
        level=logging.DEBUG,  # Capture debug and above as breadcrumbs
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
    _json_ipc = False  # TODO: Oh no... #1754

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
    def pause_all_logging_while(cls):
        former_observers = tuple(globalLogPublisher._observers)
        for observer in former_observers:
            globalLogPublisher.removeObserver(observer)
        yield
        for observer in former_observers:
            globalLogPublisher.addObserver(observer)

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
    try:
        from sentry_sdk import capture_exception, add_breadcrumb
    except ImportError:
        raise ImportError('Sentry SDK is not installed. Please install it and try again.')

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


def get_json_file_observer(name=DEFAULT_JSON_LOG_FILENAME, path=USER_LOG_DIR):
    _ensure_dir_exists(path)
    logfile = LogFile(name=name, directory=path, rotateLength=MAXIMUM_LOG_SIZE, maxRotatedFiles=MAX_LOG_FILES)
    observer = jsonFileLogObserver(outFile=logfile)
    return observer


def get_text_file_observer(name=DEFAULT_LOG_FILENAME, path=USER_LOG_DIR):
    _ensure_dir_exists(path)
    logfile = LogFile(name=name, directory=path, rotateLength=MAXIMUM_LOG_SIZE, maxRotatedFiles=MAX_LOG_FILES)
    observer = FileLogObserver(formatEvent=formatEventAsClassicLogText, outFile=logfile)
    return observer


class Logger(TwistedLogger):
    """Drop-in replacement of Twisted's Logger, patching the emit() method to tolerate inputs with curly braces,
    i.e., not compliant with PEP 3101.

    See Issue #724 and, particularly, https://github.com/nucypher/nucypher/issues/724#issuecomment-600190455"""

    @classmethod
    def escape_format_string(cls, string):
        """
        Escapes all curly braces from a PEP-3101's format string.
        """
        escaped_string = string.replace("{", "{{").replace("}", "}}")
        return escaped_string

    def emit(self, level, format=None, **kwargs):
        clean_format = self.escape_format_string(str(format))
        super().emit(level=level, format=clean_format, **kwargs)
