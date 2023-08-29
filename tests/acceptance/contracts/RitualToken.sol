// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @notice Contract for testing the application contract
 */
contract RitualToken is ERC20("RitualToken", "RT") {
    constructor(uint256 _totalSupplyOfTokens) {
        _mint(msg.sender, _totalSupplyOfTokens);
    }
}
