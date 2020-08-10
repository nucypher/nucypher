// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity ^0.7.0;

interface TokenManager {

    function mint(address _receiver, uint256 _amount) external;
    function issue(uint256 _amount) external;
    function assign(address _receiver, uint256 _amount) external;
    function burn(address _holder, uint256 _amount) external;

}
