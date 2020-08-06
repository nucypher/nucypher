// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/proxy/Upgradeable.sol";


/**
* @dev Contract that could be destroyed by selfdestruct
*/
contract Destroyable is Upgradeable {

    uint256 public constructorValue;
    uint256 public functionValue;

    constructor(uint256 _constructorValue) {
        constructorValue = _constructorValue;
    }

    function setFunctionValue(uint256 _functionValue) public {
        functionValue = _functionValue;
    }

    function verifyState(address _testTarget) public override {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.constructorValue.selector) == constructorValue);
        require(delegateGet(_testTarget, this.functionValue.selector) == functionValue);
    }

    function finishUpgrade(address _target) public override {
        super.finishUpgrade(_target);
        constructorValue = Destroyable(_target).constructorValue();
    }

    function destroy() public {
        selfdestruct(msg.sender);
    }

}
