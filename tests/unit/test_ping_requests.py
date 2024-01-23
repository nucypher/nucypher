import pytest


@pytest.fixture
def simulate_request(ursulas):
    ursula = ursulas[0]

    def request_simulator(headers):
        with ursula.rest_app.test_client() as client:
            response = client.get("/ping", headers=headers)
        return response

    return request_simulator


header_combinations = [
    ({}, 502, None),
    ({"X-Forwarded-For": "10.10.5.1, 192.168.1.1"}, 502, None),
    ({"X-Forwarded-For": "10.10.5.1, 65.0.113.0"}, 200, b"65.0.113.0"),
    ({"X-Real-IP": "65.0.113.0"}, 200, b"65.0.113.0"),
    ({"X-Forwarded-For": "10.10.5.1, 192.168.1.1"}, 502, None),
    ({"X-Forwarded-For": "10.10.5.1, 65.0.113.0"}, 200, b"65.0.113.0"),
    ({"X-Real-IP": "65.0.113.0"}, 200, b"65.0.113.0"),
    ({"X-Forwarded-For": "::ffff:192.168.1.1"}, 502, None),
    ({"X-Forwarded-For": "::ffff:8.8.8.8"}, 200, b"8.8.8.8"),
    ({"X-Real-IP": "::ffff:8.8.8.8"}, 200, b"8.8.8.8"),
    ({"X-Forwarded-For": "invalid_ip_address"}, 400, None),
    ({"X-Real-IP": "invalid_ip_address"}, 400, None),
    ({"X-Forwarded-For": "172.16.0.1, ::ffff:10.0.0.1"}, 502, None),
    ({"X-Real-IP": "172.16.0.1, ::ffff:10.0.0.1"}, 502, None),
    ({"X-Forwarded-For": "65.0.113.100"}, 200, b"65.0.113.100"),
    ({"X-Forwarded-For": "::ffff:65.0.113.100"}, 200, b"65.0.113.100"),
    ({"X-Forwarded-For": "65.0.113.100, 192.168.1.1"}, 200, b"65.0.113.100"),
    ({"X-Real-IP": "65.0.113.100, 192.168.1.1"}, 200, b"65.0.113.100"),
    ({"X-Forwarded-For": "192.168.1.1, 203.0.113.100"}, 502, None),
]


@pytest.mark.parametrize("headers, expected_status, expected_data", header_combinations)
def test_request_headers(simulate_request, headers, expected_status, expected_data):
    response = simulate_request(headers=headers)
    assert response.status_code == expected_status
    if expected_data is not None:
        assert bytes(response.data) == expected_data


def test_request_with_private_ip_only(simulate_request):
    response = simulate_request(headers={"X-Forwarded-For": "10.10.5.1, 192.168.1.1"})
    assert response.status_code == 502


def test_multi_hop_proxied_request(simulate_request):
    response = simulate_request(
        headers={"X-Forwarded-For": "10.10.5.1, 192.168.1.1, 65.0.113.0"}
    )
    assert response.status_code == 200
    assert bytes(response.data) == b"65.0.113.0"


def test_request_with_public_ip_only(simulate_request):
    response = simulate_request(
        headers={"X-Forwarded-For": "65.0.113.0", "X-Real-IP": "10.10.5.1"}
    )
    assert response.status_code == 200
    assert bytes(response.data) == b"65.0.113.0"


def test_request_with_multiple_ips(simulate_request):
    response = simulate_request(
        headers={
            "X-Forwarded-For": "192.168.2.155, 205.0.113.0",
            "X-Real-IP": "10.10.5.1",
        }
    )
    assert response.status_code == 200
    assert bytes(response.data) == b"205.0.113.0"


def test_request_with_single_public_ip(simulate_request):
    response = simulate_request(headers={"X-Forwarded-For": "65.0.113.0"})
    assert response.status_code == 200
    assert bytes(response.data) == b"65.0.113.0"


def test_resolve_ipv4_with_private_ipv4_mapped_ipv6(simulate_request):
    ipv4_mapped = "::ffff:192.0.2.128"
    response = simulate_request(headers={"X-Real-IP": ipv4_mapped})
    assert response.status_code == 502
    assert bytes(response.data) == b"No public IPv4 address detected."


def test_resolve_ipv4_with_public_ipv4_mapped_ipv6(simulate_request):
    ipv4_mapped = "::ffff:65.34.5.211"
    response = simulate_request(headers={"X-Forwarded-For": ipv4_mapped})
    assert response.status_code == 200
    assert bytes(response.data) == b"65.34.5.211"


def test_resolve_ipv4_with_malformed_ipv4_mapped_ipv6(simulate_request):
    invalid_ipv4_mapped = "::ffff:999.999.999.999"
    response = simulate_request(headers={"X-Forwarded-For": invalid_ipv4_mapped})
    assert response.status_code == 400
