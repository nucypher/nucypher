import pathlib
import sys
from contextlib import contextmanager
from enum import Enum
from typing import Callable

from twisted.logger import (
    FileLogObserver,
    LogEvent,
    LogLevel,
    formatEventAsClassicLogText,
    globalLogPublisher,
    jsonFileLogObserver,
    textFileLogObserver,
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
    _observers = dict()

    class LoggingType(Enum):
        CONSOLE = "console"
        TEXT = "text"
        JSON = "json"
        SENTRY = "sentry"

    @classmethod
    def set_log_level(cls, log_level_name):
        cls.log_level = LogLevel.levelWithName(log_level_name)

    @classmethod
    def _stop_logging(cls, logging_type: LoggingType):
        observer = cls._observers.pop(logging_type, None)
        if observer:
            globalLogPublisher.removeObserver(observer)

    @classmethod
    def _is_already_configured(cls, logging_type: LoggingType) -> bool:
        return logging_type in cls._observers

    @classmethod
    def _start_logging(cls, logging_type: LoggingType):
        if cls._is_already_configured(logging_type):
            # no-op
            return

        if logging_type == cls.LoggingType.CONSOLE:
            observer = textFileLogObserver(sys.stdout)
        elif logging_type == cls.LoggingType.TEXT:
            observer = get_text_file_observer()
        elif logging_type == cls.LoggingType.JSON:
            observer = get_json_file_observer()
        else:
            # sentry
            observer = sentry_observer

        # wrap to adhere to log level since other loggers rely on observer to differentiate
        wrapped_observer = observer_log_level_wrapper(observer)

        globalLogPublisher.addObserver(wrapped_observer)
        cls._observers[logging_type] = wrapped_observer

    @classmethod
    def start_console_logging(cls):
        cls._start_logging(cls.LoggingType.CONSOLE)

    @classmethod
    def stop_console_logging(cls):
        cls._stop_logging(cls.LoggingType.CONSOLE)

    @classmethod
    def start_text_file_logging(cls):
        cls._start_logging(cls.LoggingType.TEXT)

    @classmethod
    def stop_text_file_logging(cls):
        cls._stop_logging(cls.LoggingType.TEXT)

    @classmethod
    def start_json_file_logging(cls):
        cls._start_logging(cls.LoggingType.JSON)

    @classmethod
    def stop_json_file_logging(cls):
        cls._stop_logging(cls.LoggingType.JSON)

    @classmethod
    def start_sentry_logging(cls, dsn: str):
        _SentryInitGuard.init(dsn)
        cls._start_logging(cls.LoggingType.SENTRY)

    @classmethod
    def stop_sentry_logging(cls):
        cls._stop_logging(cls.LoggingType.SENTRY)

    @classmethod
    @contextmanager
    def pause_all_logging_while(cls):
        all_former_observers = tuple(globalLogPublisher._observers)
        former_global_observers = dict(cls._observers)
        for observer in all_former_observers:
            globalLogPublisher.removeObserver(observer)
        cls._observers.clear()

        yield
        cls._observers.clear()
        for observer in all_former_observers:
            globalLogPublisher.addObserver(observer)
        cls._observers.update(former_global_observers)


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
        from sentry_sdk import add_breadcrumb, capture_exception
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
        if level >= GlobalLoggerSettings.log_level:
            clean_format = self.escape_format_string(str(format))
            super().emit(level=level, format=clean_format, **kwargs)


def observer_log_level_wrapper(observer: Callable[[LogEvent], None]):
    def log_level_wrapper(event: LogEvent):
        if event["log_level"] >= GlobalLoggerSettings.log_level:
            observer(event)

    return log_level_wrapper
