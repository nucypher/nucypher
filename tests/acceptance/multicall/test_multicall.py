from multicall import Call, Multicall


def test_multicall_acceptance(testerchain, deploy_contracts):
    token_address = deploy_contracts["NuCypherToken"].address
    token_owner_address = testerchain.etherbase_account

    multi = Multicall(
        testerchain.w3,
        [
            Call(token_address, "totalSupply()(uint256)", [["supply", None]]),
            Call(
                token_address,
                ["balanceOf(address)(uint256)", token_owner_address],
                [["balance", None]],
            ),
        ],
    )

    result = multi()

    assert isinstance(result["supply"], int)
    assert isinstance(result["balance"], int)
