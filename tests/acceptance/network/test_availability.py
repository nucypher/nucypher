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

import maya
import pytest
import pytest_twisted as pt
import time
from flask import Response
from twisted.internet import threads

from nucypher.network.middleware import NucypherMiddlewareClient, RestMiddleware
from nucypher.network.trackers import AvailabilityTracker
from tests.utils.ursula import start_pytest_ursula_services


@pytest.mark.skip('See #2024 - skipped tests')
@pt.inlineCallbacks
def test_availability_tracker_success(blockchain_ursulas):

    # Start up self-services
    ursula = blockchain_ursulas.pop()
    start_pytest_ursula_services(ursula=ursula)

    ursula._availability_tracker = AvailabilityTracker(ursula=ursula)

    def measure():
        ursula._availability_tracker.start()
        assert ursula._availability_tracker.score == 10
        ursula._availability_tracker.record(False)
        assert ursula._availability_tracker.score == 9.0
        for i in range(7):
            ursula._availability_tracker.record(True)
        assert ursula._availability_tracker.score > 9.5

    def maintain():
        tracker = ursula._availability_tracker
        tracker.maintain()

        # The node goes offline for some time...
        for _ in range(10):
            ursula._availability_tracker.record(False, reason={'error': 'fake failure reason'})

        assert tracker.score < 4
        assert tracker.status() == (tracker.score > (tracker.SENSITIVITY * tracker.MAXIMUM_SCORE))
        assert not tracker.status()

        original_issuer = AvailabilityTracker.issue_warnings
        warnings = dict()
        def issue_warnings(tracker, *args, **kwargs):
            result = original_issuer(tracker, *args, **kwargs)
            warnings[tracker.score] = result
        AvailabilityTracker.issue_warnings = issue_warnings
        tracker.maintain()
        assert warnings
        AvailabilityTracker.issue_warnings = original_issuer

        # to keep this test fast, were just checking for a single entry
        # (technically there will be 10, but resolution is one second.)
        assert len(tracker.excuses) > 0

    def raise_to_maximum():
        tracker = ursula._availability_tracker
        for i in range(150):
            tracker.record(True)
        assert tracker.score > 9.98
        assert tracker.status() == bool(tracker.score > (tracker.SENSITIVITY * tracker.MAXIMUM_SCORE))
        assert tracker.status()

    # Run the Callbacks
    try:
        d = threads.deferToThread(measure)
        yield d
        d = threads.deferToThread(maintain)
        yield d
        d = threads.deferToThread(raise_to_maximum)
        yield d
    finally:
        if ursula._availability_tracker:
            ursula._availability_tracker.stop()
            ursula._availability_tracker = None


@pytest.mark.skip('See #2024 - skipped tests')
@pt.inlineCallbacks
def test_availability_tracker_integration(blockchain_ursulas, monkeypatch):

    # Start up self-services
    ursula = blockchain_ursulas.pop()
    start_pytest_ursula_services(ursula=ursula)

    ursula._availability_tracker = AvailabilityTracker(ursula=ursula)

    def maintain():
        tracker = ursula._availability_tracker

        def mock_node_information_endpoint(middleware, port, *args, **kwargs):
            ursula_were_looking_for = ursula.rest_interface.port == port
            if ursula_were_looking_for:
                raise RestMiddleware.NotFound("Fake Reason")  # Make this node unreachable
            else:
                response = Response(response=bytes(ursula.metadata()), mimetype='application/octet-stream')
                return response

        # apply the monkeypatch for requests.get to mock_get
        monkeypatch.setattr(NucypherMiddlewareClient,
                            NucypherMiddlewareClient.node_information.__name__,
                            mock_node_information_endpoint)

        ursula._availability_tracker.start()
        tracker.measure_sample()  # This makes a REST Call

        start, timeout = maya.now(), 1  # seconds
        while True:
            try:
                assert len(tracker.excuses)
            except AssertionError:
                now = maya.now()
                if (now - start).total_seconds() > timeout:
                    pytest.fail()
                time.sleep(0.1)
                continue
            else:
                break

    # Run the Callbacks
    try:
        d = threads.deferToThread(maintain)
        yield d
    finally:
        if ursula._availability_tracker:
            ursula._availability_tracker.stop()
            ursula._availability_tracker = None
