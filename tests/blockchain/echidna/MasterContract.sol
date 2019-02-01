pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/UserEscrow.sol";
import "contracts/UserEscrowProxy.sol";
import "./Fixtures.sol";


/**
* @notice Contract to prepare all contracts on-chain for tests
* @dev Inherit one or many of child contracts choosing which ABI must be tested
**/
contract MasterContract {

    NuCypherToken token;
    MinersEscrow escrow;
    PolicyManager policyManager;
    UserEscrow userEscrow;

    /**
    * @notice Builds main contracts
    * @dev Value 0x0 means default contract
    * Don't use custom escrow with default token or custom policy manager with default miners escrow
    **/
    function build(address _token, address _escrow, address _policyManager) internal {
        token = _token != 0x0 ? NuCypherToken(_token) : Fixtures.createDefaultToken();
        escrow = _escrow != 0x0 ? MinersEscrow(_escrow) : Fixtures.createDefaultMinersEscrow(token);
        policyManager = _policyManager != 0x0 ? PolicyManager(_policyManager) :
            Fixtures.createDefaultPolicyManager(escrow);
        if (address(escrow.policyManager()) == 0x0) {
            escrow.setPolicyManager(PolicyManagerInterface(address(policyManager)));
        }

        token.transfer(address(escrow), 100000);
        escrow.initialize();
    }

    /**
    * @notice Builds main contracts and one UserEscrow
    * @dev Value 0x0 means default contract
    * Don't use custom escrow with default token, custom policy manager with default miners escrow
    * or custom user escrow with any other default
    **/
    function build(address _token, address _escrow, address _policyManager, address _userEscrow) internal {
        build(_token, _escrow, _policyManager);
        userEscrow = _userEscrow != 0x0 ? UserEscrow(_userEscrow) :
            new UserEscrow(Fixtures.createDefaultUserEscrowLinker(token, escrow, policyManager), token);
    }

}


/**
* @notice ABI for test NuCypherToken using MasterContract
**/
contract NuCypherTokenABI is MasterContract {

    function transfer(address to, uint256 value) public returns (bool) {
        return token.transfer(to, value);
    }
    function transferFrom(address from, address to, uint256 value) public returns (bool) {
        return token.transferFrom(from, to, value);
    }
    function approve(address spender, uint256 value) public returns (bool) {
        return token.approve(spender, value);
    }
    function approveAndCall(address _spender, uint256 _value, bytes _extraData) public returns (bool success) {
        return token.approveAndCall(_spender, _value, _extraData);
    }
}


/**
* @notice ABI for test MinersEscrow using MasterContract
**/
contract MinersEscrowABI is MasterContract {

    function initialize() public {
        escrow.initialize();
    }
    function preDeposit(address[] _miners, uint256[] _values, uint16[] _periods) public {
        escrow.preDeposit(_miners, _values, _periods);
    }
    function receiveApproval(address _from, uint256 _value, address _tokenContract, bytes _extraData) public {
        escrow.receiveApproval(_from, _value, _tokenContract, _extraData);
    }
    function deposit(uint256 _value, uint16 _periods) public {
        escrow.deposit(_value, _periods);
    }
    function lock(uint256 _value, uint16 _periods) public {
        escrow.lock(_value, _periods);
    }
    function divideStake(uint256 _index, uint256 _newValue, uint16 _periods) public {
        escrow.divideStake(_index, _newValue, _periods);
    }
    function withdraw(uint256 _value) public {
        escrow.withdraw(_value);
    }
    function confirmActivity() public {
        escrow.confirmActivity();
    }
    function mint() public {
        escrow.mint();
    }
    //function setPolicyManager(PolicyManagerInterface _policyManager) external; // TODO ???
    //function verifyState(address _testTarget) public; // TODO ???
    //function finishUpgrade(address _target) public; // TODO ???
}


/**
* @notice ABI for test PolicyManager using MasterContract
**/
contract PolicyManagerABI is MasterContract {

    function register(address _node, uint16 _period) public {
        policyManager.register(_node, _period);
    }
    function setMinRewardRate(uint256 _minRewardRate) public {
        policyManager.setMinRewardRate(_minRewardRate);
    }
    function createPolicy(
        bytes16 _policyId,
        uint16 _numberOfPeriods,
        uint256 _firstPartialReward,
        address[] _nodes
    )
        public payable
    {
        policyManager.createPolicy(_policyId, _numberOfPeriods, _firstPartialReward, _nodes);
    }
    function updateReward(address _node, uint16 _period) public {
        policyManager.updateReward(_node, _period);
    }
    function withdraw() public returns (uint256) {
        return policyManager.withdraw();
    }
    function withdraw(address _recipient) public returns (uint256) {
        return policyManager.withdraw(_recipient);
    }
    function revokePolicy(bytes16 _policyId) public {
        policyManager.revokePolicy(_policyId);
    }
    function revokeArrangement(bytes16 _policyId, address _node) public returns (uint256 refundValue) {
        return policyManager.revokeArrangement(_policyId, _node);
    }
    function refund(bytes16 _policyId) public {
        policyManager.refund(_policyId);
    }
    function refund(bytes16 _policyId, address _node) public returns (uint256 refundValue) {
        return policyManager.refund(_policyId, _node);
    }
    //function verifyState(address _testTarget) public; // TODO ???
    //function finishUpgrade(address _target) public; // TODO ???
}


/**
* @notice ABI for test UserEscrow using MasterContract
**/
contract UserEscrowABI is MasterContract {

    function initialDeposit(uint256 _value, uint256 _duration) public {
        userEscrow.initialDeposit(_value, _duration);
    }
    function withdrawTokens(uint256 _value) public {
        userEscrow.withdrawTokens(_value);
    }
    function withdrawETH() public {
        userEscrow.withdrawETH();
    }
    function transferOwnership(address newOwner) public {
        userEscrow.transferOwnership(newOwner);
    }

}


/**
* @notice ABI for test UserEscrowProxy using MasterContract
**/
contract UserEscrowProxyABI is MasterContract {

    function depositAsMiner(uint256 _value, uint16 _periods) public {
        UserEscrowProxy(userEscrow).depositAsMiner(_value, _periods);
    }
    function withdrawAsMiner(uint256 _value) public {
        UserEscrowProxy(userEscrow).withdrawAsMiner(_value);
    }
    function lock(uint256 _value, uint16 _periods) public {
        UserEscrowProxy(userEscrow).lock(_value, _periods);
    }
    function divideStake(uint256 _index, uint256 _newValue, uint16 _periods) public{
        UserEscrowProxy(userEscrow).divideStake(_index, _newValue, _periods);
    }
    function confirmActivity() public {
        UserEscrowProxy(userEscrow).confirmActivity();
    }
    function mint() public {
        UserEscrowProxy(userEscrow).mint();
    }
    function withdrawPolicyReward() public {
        UserEscrowProxy(userEscrow).withdrawPolicyReward();
    }
    function setMinRewardRate(uint256 _minRewardRate) public {
        UserEscrowProxy(userEscrow).setMinRewardRate(_minRewardRate);
    }

}
