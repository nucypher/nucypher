from http import HTTPStatus
from urllib.parse import urlparse

import pytest

from tests.utils.middleware import MockRestMiddleware


@pytest.mark.parametrize(
    "status_code, expected_exception_class",
    [
        (HTTPStatus.BAD_REQUEST, MockRestMiddleware.BadRequest),
        (HTTPStatus.NOT_FOUND, MockRestMiddleware.NotFound),
        (HTTPStatus.PAYMENT_REQUIRED, MockRestMiddleware.PaymentRequired),
        (HTTPStatus.FORBIDDEN, MockRestMiddleware.Unauthorized),
        # catch alls
        (HTTPStatus.REQUEST_TIMEOUT, MockRestMiddleware.UnexpectedResponse),
        (HTTPStatus.INTERNAL_SERVER_ERROR, MockRestMiddleware.UnexpectedResponse),
        (HTTPStatus.NOT_IMPLEMENTED, MockRestMiddleware.UnexpectedResponse),
        (HTTPStatus.SERVICE_UNAVAILABLE, MockRestMiddleware.UnexpectedResponse),
    ],
)
def test_middleware_response_status_code_processing(
    status_code,
    expected_exception_class,
    mocker,
    mock_rest_middleware,
    ursulas,
):
    ursula = list(ursulas)[0]
    _original_execute_method = mock_rest_middleware.client._execute_method

    def execute_method_side_effect(
        node_or_sprout, host, port, method, endpoint, *args, **kwargs
    ):
        endpoint_url = urlparse(endpoint)
        if endpoint_url.path == "/reencrypt":
            response = mocker.MagicMock(
                text="I have not failed. I've just found 10,000 ways that won't work.",  # -- Thomas Edison
                status_code=status_code,
            )
            return response
        else:
            return _original_execute_method(
                node_or_sprout, host, port, method, endpoint, *args, **kwargs
            )

    mocker.patch.object(
        mock_rest_middleware.client,
        "_execute_method",
        side_effect=execute_method_side_effect,
    )
    with pytest.raises(expected_exception_class):
        mock_rest_middleware.reencrypt(
            ursula=ursula, reencryption_request_bytes=b"reencryption_request"
        )
