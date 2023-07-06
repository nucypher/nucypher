from nucypher.policy.conditions.multicall import abi_to_signature


def test_abi_to_signature():
    erc20_balanceOf_signature = "balanceOf(address)(uint256)"
    erc20_approve_signature = "approve(address,uint256)(bool)"
    tokenStaking_stakes_signature = "stakes(address)(uint96,uint96,uint96)"

    erc20_balanceOf_abi = {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
    erc20_approve_abi = {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    }
    tokenStaking_stakes_abi = {
        "inputs": [
            {"internalType": "address", "name": "stakingProvider", "type": "address"}
        ],
        "name": "stakes",
        "outputs": [
            {"internalType": "uint96", "name": "tStake", "type": "uint96"},
            {"internalType": "uint96", "name": "keepInTStake", "type": "uint96"},
            {"internalType": "uint96", "name": "nuInTStake", "type": "uint96"},
        ],
        "stateMutability": "view",
        "type": "function",
    }

    assert erc20_balanceOf_signature == abi_to_signature(erc20_balanceOf_abi)
    assert erc20_approve_signature == abi_to_signature(erc20_approve_abi)
    assert tokenStaking_stakes_signature == abi_to_signature(tokenStaking_stakes_abi)
