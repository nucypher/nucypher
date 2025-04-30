import json
from unittest.mock import Mock, patch

import pytest
from nucypher_core import NodeMetadata

from nucypher.characters.lawful import Enrico, Ursula
from nucypher.crypto.powers import SigningPower
from nucypher.network.middleware import RestMiddleware
from nucypher.types import ThresholdSignatureRequest
from nucypher.policy.conditions.lingo import ConditionLingo, ConditionType


def test_request_threshold_signature(mocker):
    # Mock the network middleware
    mock_middleware = Mock(spec=RestMiddleware)
    
    # Create mock response for successful signature
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b"mock_signature_share"
    mock_middleware.request_signature.return_value = mock_response

    # Create mock Ursulas
    mock_ursulas = []
    for i in range(3):
        mock_ursula = Mock(spec=Ursula)
        mock_ursula.checksum_address = f"0x{i:040d}"  # Create unique addresses
        mock_ursulas.append(mock_ursula)

    # Create Enrico
    enrico = Enrico(
        encrypting_key=Mock(),  # Mock the encrypting key
        network_middleware=mock_middleware
    )

    # Test data
    data_to_sign = b"test_data"
    cohort_id = 1
    conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.TIME.value,
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": 1  # Using chain ID 1 for testing
        }
    }
    context = {"test": "context"}

    # Request threshold signature
    signature = enrico.request_threshold_signature(
        data_to_sign=data_to_sign,
        cohort_id=cohort_id,
        conditions=conditions,
        context=context,
        ursulas=mock_ursulas
    )

    # Verify middleware was called correctly for each Ursula
    assert mock_middleware.request_signature.call_count == len(mock_ursulas)
    
    # Get the actual request bytes that were passed to request_signature
    actual_request_bytes = mock_middleware.request_signature.call_args_list[0][1]['signing_request_bytes']
    actual_request = ThresholdSignatureRequest.from_bytes(actual_request_bytes)

    # Create expected request
    expected_request = ThresholdSignatureRequest(
        data_to_sign=data_to_sign,
        cohort_id=cohort_id,
        condition=json.dumps(conditions).encode(),
        context=json.dumps(context).encode()
    )

    # Compare request fields
    assert actual_request.data_to_sign == expected_request.data_to_sign
    assert actual_request.cohort_id == expected_request.cohort_id
    assert json.loads(actual_request.condition) == json.loads(expected_request.condition)
    assert json.loads(actual_request.context) == json.loads(expected_request.context)

    # Verify signature aggregation
    expected_signature = b"mock_signature_share" * len(mock_ursulas)
    assert signature == expected_signature


def test_request_threshold_signature_with_failures(mocker):
    # Mock the network middleware
    mock_middleware = Mock(spec=RestMiddleware)
    
    # Create mixed responses - some successful, some failed
    success_response = Mock()
    success_response.status_code = 200
    success_response.content = b"mock_signature_share"
    
    error_response = Mock()
    error_response.status_code = 400
    error_response.content = b"Invalid request"

    # Configure middleware to alternate between success and failure
    mock_middleware.request_signature.side_effect = [
        success_response,
        error_response,
        success_response
    ]

    # Create mock Ursulas
    mock_ursulas = []
    for i in range(3):
        mock_ursula = Mock(spec=Ursula)
        mock_ursula.checksum_address = f"0x{i:040d}"
        mock_ursulas.append(mock_ursula)

    # Create Enrico
    enrico = Enrico(
        encrypting_key=Mock(),
        network_middleware=mock_middleware
    )

    # Create valid condition lingo
    conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.TIME.value,
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": 1
        }
    }

    # Request threshold signature
    signature = enrico.request_threshold_signature(
        data_to_sign=b"test_data",
        cohort_id=1,
        conditions=conditions,
        ursulas=mock_ursulas
    )

    # Verify we got signatures from successful responses only
    expected_signature = b"mock_signature_share" * 2  # Two successful responses
    assert signature == expected_signature


def test_request_threshold_signature_all_failures(mocker):
    # Mock the network middleware
    mock_middleware = Mock(spec=RestMiddleware)
    
    # Create error response
    error_response = Mock()
    error_response.status_code = 400
    error_response.content = b"Invalid request"
    mock_middleware.request_signature.return_value = error_response

    # Create mock Ursulas
    mock_ursulas = []
    for i in range(3):
        mock_ursula = Mock(spec=Ursula)
        mock_ursula.checksum_address = f"0x{i:040d}"
        mock_ursulas.append(mock_ursula)

    # Create Enrico
    enrico = Enrico(
        encrypting_key=Mock(),
        network_middleware=mock_middleware
    )

    # Create valid condition lingo
    conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.TIME.value,
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": 1
        }
    }

    # Test that it raises an exception when all requests fail
    with pytest.raises(RuntimeError) as excinfo:
        enrico.request_threshold_signature(
            data_to_sign=b"test_data",
            cohort_id=1,
            conditions=conditions,
            ursulas=mock_ursulas
        )
    
    assert "No signatures collected" in str(excinfo.value)


def test_request_threshold_signature_with_exception(mocker):
    # Mock the network middleware
    mock_middleware = Mock(spec=RestMiddleware)
    
    # Make middleware raise an exception
    mock_middleware.request_signature.side_effect = ConnectionError("Network error")

    # Create mock Ursula
    mock_ursula = Mock(spec=Ursula)
    mock_ursula.checksum_address = "0x" + "0" * 40

    # Create Enrico
    enrico = Enrico(
        encrypting_key=Mock(),
        network_middleware=mock_middleware
    )

    # Create valid condition lingo
    conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.TIME.value,
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": 1
        }
    }

    # Test that it handles the exception gracefully
    with pytest.raises(RuntimeError) as excinfo:
        enrico.request_threshold_signature(
            data_to_sign=b"test_data",
            cohort_id=1,
            conditions=conditions,
            ursulas=[mock_ursula]
        )
    
    assert "No signatures collected" in str(excinfo.value)
    assert "Network error" in str(excinfo.value) 