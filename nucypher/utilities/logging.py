from twisted.logger import ILogObserver
from zope.interface import provider
from nucypher.config.constants import REPORT_TO_SENTRY


@provider(ILogObserver)
def simpleObserver(event):
    print(event)


if REPORT_TO_SENTRY:
    from twisted.python import log
    from sentry_sdk import Client, capture_exception, add_breadcrumb
    from nucypher.config.constants import NUCYPHER_SENTRY_ENDPOINT

    client = Client(dsn=NUCYPHER_SENTRY_ENDPOINT)

    def logToSentry(event):

        # Handle Logs
        if not event.get('isError') or 'failure' not in event:
            add_breadcrumb(event)
            return

        # Handle Failures
        f = event['failure']
        capture_exception((f.type, f.value, f.getTracebackObject()))

    log.addObserver(logToSentry)
