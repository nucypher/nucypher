from nucypher.policy.conditions.lingo import ReturnValueTest
from nucypher.policy.conditions.offchain import OffchainCondition


def test_basic_offchain_condition_evaluation(accounts, condition_providers, mocker):
    mocker.patch(
        "nucypher.policy.conditions.offchain.OffchainCondition.fetch",  # Path to the method you want to patch
        return_value=mocker.Mock(
            status_code=200, json=lambda: {"ethereum": {"usd": 0.0}}
        ),
    )

    condition = OffchainCondition(
        endpoint="https://api.coingecko.com/api/v3/simple/price",
        parameters={
            "ids": "ethereum",
            "vs_currencies": "usd",
        },
        query="ethereum.usd",
        return_value_test=ReturnValueTest("==", 0.0),
    )

    assert condition.verify() == (True, 0.0)
