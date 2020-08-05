// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


/**
* @dev Contract for reentrancy protection testing
**/
contract ReentrancyTest {

    uint256 maxDepth = 1;
    uint256 lockCounter;
    address target;
    uint256 value;
    bytes data;

    function setData(uint256 _maxDepth, address _target, uint256 _value, bytes calldata _data) external {
        maxDepth = _maxDepth;
        target = _target;
        value = _value;
        data = _data;
    }

    receive() external payable {
        // call no more than maxDepth times
        if (lockCounter >= maxDepth) {
            return;
        }
        lockCounter++;
        (bool callSuccess,) = target.call{value: value}(data);
        require(callSuccess);
        lockCounter--;
    }

}
