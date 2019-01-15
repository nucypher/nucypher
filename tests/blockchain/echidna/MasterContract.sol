pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/UserEscrow.sol";
import "contracts/UserEscrowProxy.sol";
import "./Constants.sol";


contract MasterContract is Constants {

    NuCypherToken token;
    MinersEscrow escrow;
    PolicyManager policyManager;
//    UserEscrowProxy userEscrowProxy;
//    UserEscrowLibraryLinker userEscrowLinker;
    UserEscrow userEscrow;

    constructor(address _token, address _escrow, address _policyManager) public {
        token = _token != 0x0 ? NuCypherToken(_token) : new NuCypherToken(1000000);
        escrow = _escrow != 0x0 ? MinersEscrow(_escrow) :
            new MinersEscrow(token, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 100, 1500);
        policyManager = _policyManager != 0x0 ? PolicyManager(_policyManager) : new PolicyManager(escrow);
        if (address(escrow.policyManager()) == 0x0) {
            escrow.setPolicyManager(PolicyManagerInterface(address(policyManager)));
        }
    }

}


contract NuCypherTokenABI is MasterContract {

    constructor(address _token, address _escrow, address _policyManager)
        public
        MasterContract(_token, _escrow, _policyManager)
    {
    }

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


contract MinersEscrowABI is MasterContract {

    function initialize() public {
        escrow.initialize();
    }
    function preDeposit(address[] _miners, uint256[] _values, uint16[] _periods) public {
        escrow.preDeposit(_miners, _values, _periods);
    }
    function receiveApproval(address _from, uint256 _value, address _tokenContract, bytes _extraData) external {
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
    function confirmActivity() external {
        escrow.confirmActivity();
    }
    function mint() external {
        escrow.mint();
    }
    //function setPolicyManager(PolicyManagerInterface _policyManager) external; // TODO ???
    //function verifyState(address _testTarget) public; // TODO ???
    //function finishUpgrade(address _target) public; // TODO ???
}


contract PolicyManagerABI is MasterContract {

    function register(address _node, uint16 _period) external {
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
    function updateReward(address _node, uint16 _period) external {
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

}


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
    function confirmActivity() external {
        UserEscrowProxy(userEscrow).confirmActivity();
    }
    function mint() external {
        UserEscrowProxy(userEscrow).mint();
    }
    function withdrawPolicyReward() public {
        UserEscrowProxy(userEscrow).withdrawPolicyReward();
    }
    function setMinRewardRate(uint256 _minRewardRate) public {
        UserEscrowProxy(userEscrow).setMinRewardRate(_minRewardRate);
    }

}
