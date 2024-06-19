from nucypher.policy.conditions.evm import OffchainCondition
from nucypher.policy.conditions.lingo import ReturnValueTest


def test_basic_offchain_condition_evaluation(accounts, condition_providers, mocker):

    condition = OffchainCondition(
        endpoint="https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
        return_value_test=ReturnValueTest(">", 0),
    )

    assert condition.verify() == (True, 0.0)
