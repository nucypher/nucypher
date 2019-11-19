pragma solidity ^0.5.3;


import "contracts/proxy/Upgradeable.sol";


/**
* @dev Contract that could be destroyed by selfdestruct
*/
contract Destroyable is Upgradeable {

    uint256 public constructorValue;
    uint256 public functionValue;

    constructor(uint256 _constructorValue) public {
        constructorValue = _constructorValue;
    }

    function setFunctionValue(uint256 _functionValue) public {
        functionValue = _functionValue;
    }

    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, "constructorValue()") == constructorValue);
        require(delegateGet(_testTarget, "functionValue()") == functionValue);
    }

    function finishUpgrade(address _target) public {
        super.finishUpgrade(_target);
        constructorValue = Destroyable(_target).constructorValue();
    }

    function destroy() public {
        selfdestruct(msg.sender);
    }

}
