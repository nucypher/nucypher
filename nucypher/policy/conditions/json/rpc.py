from abc import ABC
from http import HTTPMethod
from typing import Any, Optional, Tuple, override

from marshmallow import fields, post_load, validate
from marshmallow.fields import Url
from marshmallow.validate import OneOf

from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    JsonRequestException,
)
from nucypher.policy.conditions.json.base import JSONPathField, JsonRequestCall
from nucypher.policy.conditions.json.utils import process_result_for_condition_eval
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ExecutionCallAccessControlCondition,
    ReturnValueTest,
)
from nucypher.utilities.logging import Logger


class BaseJsonRPCCall(JsonRequestCall, ABC):
    class Schema(JsonRequestCall.Schema):
        method = fields.Str(required=True)
        params = fields.Field(required=False, allow_none=True)
        query = JSONPathField(required=False, allow_none=True)

    def __init__(
        self,
        method: str,
        params: Optional[Any] = None,
        query: Optional[str] = None,
    ):
        self.method = method
        self.params = params or []

        parameters = {
            "jsonrpc": "2.0",
            "method": self.method,
            "params": self.params,
            "id": 1,  # any id will do
        }
        super().__init__(
            http_method=HTTPMethod.POST,
            parameters=parameters,
            query=query,
        )

    @override
    def _execute(self, endpoint, **context):
        data = self._fetch(endpoint, **context)

        # response contains a value for either "result" or "error"
        error = data.get("error", None)
        if error:
            raise JsonRequestException(
                f"JSON RPC Request failed with error in response: {error}"
            )

        # obtain result first then perform query
        result = data["result"]
        query_result = self._query_response(result, **context)
        return query_result


class JsonEndpointRPCCall(BaseJsonRPCCall):
    class Schema(BaseJsonRPCCall.Schema):
        endpoint = Url(required=True, relative=False, schemes=["https"])

        @post_load
        def make(self, data, **kwargs):
            return JsonEndpointRPCCall(**data)

    def __init__(
        self,
        endpoint: str,
        method: str,
        params: Optional[Any] = None,
        query: Optional[str] = None,
    ):
        self.endpoint = endpoint
        super().__init__(method=method, params=params, query=query)

    @override
    def execute(self, **context) -> Any:
        return super()._execute(endpoint=self.endpoint, **context)


class JsonRPRCCondition(ExecutionCallAccessControlCondition):
    EXECUTION_CALL_TYPE = JsonEndpointRPCCall
    CONDITION_TYPE = ConditionType.JSONRPC.value

    class Schema(
        ExecutionCallAccessControlCondition.Schema, JsonEndpointRPCCall.Schema
    ):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.JSONRPC.value), required=True
        )

        @post_load
        def make(self, data, **kwargs):
            return JsonRPRCCondition(**data)

    def __init__(
        self,
        endpoint: str,
        method: str,
        return_value_test: ReturnValueTest,
        params: Optional[Any] = None,
        query: Optional[str] = None,
        condition_type: str = ConditionType.JSONRPC.value,
    ):
        self.endpoint = endpoint
        super().__init__(
            endpoint=endpoint,
            method=method,
            params=params,
            query=query,
            condition_type=condition_type,
            return_value_test=return_value_test,
        )

    @property
    def method(self):
        return self.execution_call.method

    @property
    def params(self):
        return self.execution_call.params

    @property
    def query(self):
        return self.execution_call.query

    @property
    def timeout(self):
        return self.execution_call.timeout

    def verify(self, **context) -> Tuple[bool, Any]:
        result = self.execution_call.execute(**context)
        result_for_eval = process_result_for_condition_eval(result)

        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        eval_result = resolved_return_value_test.eval(result_for_eval)  # test
        return eval_result, result


class NonEvmJsonRPCCall(BaseJsonRPCCall):
    class Schema(BaseJsonRPCCall.Schema):
        blockchain = fields.Str(required=True, validate=OneOf(["solana", "bitcoin"]))

        @post_load
        def make(self, data, **kwargs):
            return NonEvmJsonRPCCall(**data)

    def __init__(
        self,
        blockchain: str,
        method: str,
        params: Optional[Any] = None,
        query: Optional[str] = None,
    ):
        self.blockchain = blockchain
        super().__init__(method=method, params=params, query=query)

    @override
    def execute(self, endpoint, **context) -> Any:
        return self._execute(endpoint, **context)


class NonEvmJsonRPCCondition(ExecutionCallAccessControlCondition):
    EXECUTION_CALL_TYPE = NonEvmJsonRPCCall
    CONDITION_TYPE = ConditionType.NON_EVM_JSON_RPC.value

    # TODO: this should be moved to `nucypher/chainlist`; here for now for POC
    BLOCKCHAINS = {
        "solana": [
            "https://api.mainnet-beta.solana.com",
            "https://solana.drpc.org",
        ],
        "bitcoin": [
            "https://docs-demo.btc.quiknode.pro/",
            "https://bitcoin.drpc.org",
        ],
    }

    class Schema(ExecutionCallAccessControlCondition.Schema, NonEvmJsonRPCCall.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.NON_EVM_JSON_RPC.value), required=True
        )

        @post_load
        def make(self, data, **kwargs):
            return NonEvmJsonRPCCondition(**data)

    def __init__(
        self,
        blockchain: str,
        method: str,
        return_value_test: ReturnValueTest,
        query: Optional[str] = None,
        params: Optional[Any] = None,
        condition_type: str = ConditionType.NON_EVM_JSON_RPC.value,
        name: Optional[str] = None,
    ):
        self.logger = Logger(__name__)
        super().__init__(
            blockchain=blockchain,
            method=method,
            return_value_test=return_value_test,
            query=query,
            params=params,
            condition_type=condition_type,
            name=name,
        )

    @property
    def blockchain(self):
        return self.execution_call.blockchain

    @property
    def method(self):
        return self.execution_call.method

    @property
    def params(self):
        return self.execution_call.params

    @property
    def query(self):
        return self.execution_call.query

    @property
    def timeout(self):
        return self.execution_call.timeout

    def verify(self, **context) -> Tuple[bool, Any]:
        blockchain_urls = self.BLOCKCHAINS[self.blockchain]
        latest_error = ""
        for url in blockchain_urls:
            try:
                result = self.execution_call.execute(endpoint=url, **context)
                break
            except JsonRequestException as e:
                latest_error = f"Non-evm RPC call to {url} failed: {e}"
                self.logger.warn(f"{latest_error}, attempting to try next endpoint.")
                continue
        else:
            raise ConditionEvaluationFailed(
                f"Unable to execute non-evm JSON RPC call using {blockchain_urls}; latest error - {latest_error}"
            )

        result_for_eval = process_result_for_condition_eval(result)

        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        eval_result = resolved_return_value_test.eval(result_for_eval)  # test
        return eval_result, result
