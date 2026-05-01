import pytest

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.actors import Operator


class TestConditionProviderChainValidation:
    @pytest.fixture
    def mock_operator(self, mocker):
        operator = mocker.Mock(spec=Operator)
        operator.domain = domains.MAINNET
        operator.ActorError = Operator.ActorError
        operator.log = mocker.Mock()
        return operator

    def test_missing_mandatory_chain_raises_error(self, mock_operator):
        endpoints = {1: ["http://eth.example.com"]}
        with pytest.raises(Operator.ActorError, match="missing mandatory chains"):
            Operator.get_condition_provider_manager(mock_operator, endpoints)

    def test_additional_chains_pass_validation(self, mock_operator, mocker):
        endpoints = {1: ["http://eth"], 137: ["http://poly"], 8453: ["http://base"]}

        mocker.patch(
            "nucypher.blockchain.eth.actors.rpc_endpoint_health_check",
            return_value=True,
        )
        mocker.patch(
            "nucypher.blockchain.eth.actors.get_healthy_default_rpc_endpoints",
            return_value={},
        )
        Operator.get_condition_provider_manager(mock_operator, endpoints)

    def test_failed_rpc_health_user_configured_endpoint_raises_error(
        self, mock_operator, mocker
    ):
        poly2_uri = "http://poly2"
        user_configured_endpoints = {
            1: ["http://eth"],
            137: ["http://poly1", poly2_uri],
        }

        def mock_rpc_endpoint_health_check(endpoint: str, *args, **kwargs):
            if endpoint == poly2_uri:
                return False
            return True

        rpc_endpoint_health_check_mock = mocker.patch(
            "nucypher.blockchain.eth.actors.rpc_endpoint_health_check",
            side_effect=mock_rpc_endpoint_health_check,
        )
        mocker.patch(
            "nucypher.blockchain.eth.actors.get_healthy_default_rpc_endpoints",
            return_value={},
        )

        with pytest.raises(
            Operator.ActorError,
            match=f"Operator-configured.*{poly2_uri}.*{137}.*is unhealthy",
        ):
            Operator.get_condition_provider_manager(
                mock_operator, user_configured_endpoints
            )

        assert rpc_endpoint_health_check_mock.call_count == 3  # 3 endpoints checked

    def test_failed_rpc_health_default_endpoints_does_not_raise_error(
        self, mock_operator, mocker
    ):
        poly_public_rpc = "http://default-poly"
        mocker.patch(
            "nucypher.blockchain.eth.utils.get_default_rpc_endpoints",
            return_value={137: [poly_public_rpc]},
        )

        def mock_rpc_endpoint_health_check(endpoint: str, *args, **kwargs):
            if endpoint == poly_public_rpc:
                return False
            return True

        user_configured_rpc_endpoint_health_check_mock = mocker.patch(
            "nucypher.blockchain.eth.actors.rpc_endpoint_health_check",
            side_effect=mock_rpc_endpoint_health_check,
        )
        default_endpoint_rpc_health_check_mock = mocker.patch(
            "nucypher.blockchain.eth.utils.rpc_endpoint_health_check",
            side_effect=mock_rpc_endpoint_health_check,
        )

        # user-configured endpoint is healthy, but the default endpoint is not healthy.
        # This should not raise an exception because the default endpoint is not required to be healthy.
        user_configured_endpoints = {1: ["http://eth"], 137: ["http://poly1"]}
        Operator.get_condition_provider_manager(
            mock_operator, user_configured_endpoints
        )

        assert (
            user_configured_rpc_endpoint_health_check_mock.call_count == 2
        )  # 2 user-configured endpoints checked
        assert (
            default_endpoint_rpc_health_check_mock.call_count == 1
        )  # 1 default endpoint checked
