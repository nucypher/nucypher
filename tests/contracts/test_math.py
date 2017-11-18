import math


def test_math(chain):
    """
    These are tests for math library
    """

    math_contract, _ = chain.provider.get_or_deploy_contract('ExponentMathTest')

    assert int(math.exp(2)) == int(math_contract.call().exp(2, 100, 1, 30) / 100)
    assert int(math.exp(2.5)) == int(math_contract.call().exp(25, 100, 10, 30) / 100)
    assert int(math.exp(10)) == int(math_contract.call().exp(10, 100, 1, 30) / 100)

    assert int(1000 * (1 - math.exp(-2))) == \
        math_contract.call().exponentialFunction(2, 1000, 1, 200, 30)
    assert int(1000 * (1 - math.exp(-2.5))) == \
        math_contract.call().exponentialFunction(25, 1000, 10, 200, 30)
    assert int(10 ** 9 * (1 - math.exp(-0.0000001))) == \
        math_contract.call().exponentialFunction(10, 10 ** 9, 10 ** 8, 10 ** 8, 30)
    # assert int(10 ** 9 * (1 - math.exp(-0.00000001))) == \
    #     math_contract.call().exponentialFunction(1, 10 ** 9, 10 ** 8, 10 ** 8, 30)
    # assert int(10 ** 9 * (1 - math.exp(-10))) == \
    #     math_contract.call().exponentialFunction(10 ** 9, 10 ** 9, 10 ** 8, 10 ** 8, 30)
