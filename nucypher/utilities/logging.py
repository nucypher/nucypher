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


from sentry_sdk import Client, capture_exception, add_breadcrumb
from twisted.logger import ILogObserver
from zope.interface import provider


@provider(ILogObserver)
def simpleObserver(event):
    message = '{} ({}): {}'.format(event.get('log_level').name.upper(),
                                   event.get('log_namespace'),
                                   event.get('log_format'))
    print(message)


def logToSentry(event):

    # Handle Logs
    if not event.get('isError') or 'failure' not in event:
        add_breadcrumb(level=event.get('log_level').name,
                       message=event.get('log_format'),
                       category=event.get('log_namespace'))
        return

    # Handle Failures
    f = event['failure']
    capture_exception((f.type, f.value, f.getTracebackObject()))
