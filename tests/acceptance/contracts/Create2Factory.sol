// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin530/contracts/utils/Create2.sol";

contract Create2Factory {
    function computeAddress(
        bytes32 salt,
        bytes32 bytecodeHash,
        address deployer
    ) external pure returns (address) {
        return Create2.computeAddress(salt, bytecodeHash, deployer);
    }
}
