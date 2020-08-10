// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


/**
* @notice Contract for testing interactions with the TokenManager
*/
contract TokenManagerMock {

    mapping (address => uint256) balance;

    function mint(address _receiver, uint256 _amount) external {
        balance[_receiver] += _amount;
    }

    function issue(uint256 _amount) external {
        balance[address(this)] += _amount;
    }

    function assign(address _receiver, uint256 _amount) external {
        balance[address(this)] -= _amount;
        balance[_receiver] += _amount;
    }

    function burn(address _holder, uint256 _amount) external {
        balance[_holder] -= _amount;
    }

}
