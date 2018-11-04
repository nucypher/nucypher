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

from nucypher.__about__ import (
    __author__,  __license__, __summary__, __title__, __version__, __copyright__, __email__, __url__
)


__all__ = [
    "__title__", "__summary__", "__version__", "__author__", "__license__", "__copyright__", "__email__", "__url__"
]


# Set Default Curve #
#####################

from umbral.config import set_default_curve
set_default_curve()


# Report to Sentry #
####################

from nucypher.config.constants import REPORT_TO_SENTRY, NUCYPHER_SENTRY_ENDPOINT, PACKAGE_NAME

try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
except ImportError:
    if REPORT_TO_SENTRY is True:
        raise ImportError("Sentry")
else:
    import logging
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.DEBUG  # Send debug logs as events
    )
    sentry_sdk.init(
        dsn=NUCYPHER_SENTRY_ENDPOINT,
        integrations=[sentry_logging],
        release='{}@{}'.format(PACKAGE_NAME, __version__)
    )


# Twisted Log Observer #
########################

from nucypher.utilities.logging import simpleObserver
from twisted.logger import globalLogPublisher

globalLogPublisher.addObserver(simpleObserver)
