"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import datetime
import pathlib

from sentry_sdk import capture_exception, add_breadcrumb
from twisted.logger import FileLogObserver, jsonFileLogObserver
from twisted.python.log import ILogObserver
from twisted.python.logfile import DailyLogFile
from zope.interface import provider

from nucypher.config.constants import USER_LOG_DIR


def formatUrsulaLogEvent(event):
    """
    Format log lines for file logging.
    """
    human_time = datetime.datetime.fromtimestamp(event.get('log_time')).strftime('%c')

    log_line = '{} [{}] ({}): {}\n'.format(event.get('log_level').name.upper(),
                                           human_time,
                                           event.get('log_namespace'),
                                           event.get('log_format'))
    return log_line


def _get_or_create_user_log_dir():
    return pathlib.Path(USER_LOG_DIR).mkdir(parents=True, exist_ok=True)


def getJsonFileObserver():
    _get_or_create_user_log_dir()
    logfile = DailyLogFile("ursula.log.json", USER_LOG_DIR)
    observer = jsonFileLogObserver(outFile=logfile)
    return observer


def getTextFileObserver():
    _get_or_create_user_log_dir()
    logfile = DailyLogFile("ursula.log", USER_LOG_DIR)
    observer = FileLogObserver(formatEvent=formatUrsulaLogEvent, outFile=logfile)
    return observer


@provider(ILogObserver)
def simpleObserver(event):
    message = '{level} ({source}): {message}'.format(level=event.get('log_level').name.upper(),
                                                     source=event.get('log_namespace'),
                                                     message=event.get('log_format'))
    print(message)


@provider(ILogObserver)
def logToSentry(event):
    """
    Twisted observer for Sentry...
    Capture tracebacks and leave a trail of breadcrumbs.
    """

    # Handle Logs
    if not event.get('isError') or 'failure' not in event:
        add_breadcrumb(level=event.get('log_level').name,
                       message=event.get('log_format'),
                       category=event.get('log_namespace'))
        return

    # Handle Failures
    f = event['failure']
    capture_exception((f.type, f.value, f.getTracebackObject()))
