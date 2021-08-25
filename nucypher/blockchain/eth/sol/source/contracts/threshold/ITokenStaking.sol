// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
* @notice TokenStaking interface
*/
interface ITokenStaking {
    // TODO remove
    function allocatedPerApp(address) external view returns (uint256);
    function getAllocated(address, address) external view returns (uint256);
}
