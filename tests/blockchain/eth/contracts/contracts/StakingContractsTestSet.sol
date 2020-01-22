pragma solidity ^0.6.1;


import "contracts/NuCypherToken.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";


/**
* @notice Contract for using in staking contracts tests
*/
contract StakingEscrowForStakingContractMock {

    NuCypherToken token;
    uint32 public secondsPerPeriod = 1;
    address public node;
    uint256 public value;
    uint256 public lockedValue;
    uint16 public periods;
    uint256 public index;
    bool public reStake;
    uint16 public lockReStakeUntilPeriod;
    address public worker;
    bool public windDown;

    constructor(NuCypherToken _token) public {
        token = _token;
    }

    function deposit(uint256 _value, uint16 _periods) external {
        deposit(msg.sender, _value, _periods);
    }

    function deposit(address _node, uint256 _value, uint16 _periods) public {
        node = _node;
        value += _value;
        lockedValue += _value;
        periods += _periods;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function lock(uint256 _value, uint16 _periods) external {
        lockedValue += _value;
        periods += _periods;
    }

    function divideStake(uint256 _index, uint256 _newValue, uint16 _periods) external {
        index = _index;
        lockedValue += _newValue;
        periods += _periods;
    }

    function withdraw(uint256 _value) public {
        value -= _value;
        token.transfer(msg.sender, _value);
    }

    function withdrawAll() external {
        withdraw(value);
    }

    function mint() external {
        value += 1000;
    }

    function setReStake(bool _reStake) external {
        reStake = _reStake;
    }

    function lockReStake(uint16 _lockReStakeUntilPeriod) external {
        lockReStakeUntilPeriod = _lockReStakeUntilPeriod;
    }

    function setWorker(address _worker) external {
        worker = _worker;
    }

    function prolongStake(uint256 _index, uint16 _periods) external {
        index = _index;
        periods += _periods;
    }

    function getAllTokens(address) external view returns (uint256) {
        return value;
    }

    function setWindDown(bool _windDown) external {
        windDown = _windDown;
    }
}


/**
* @notice Contract for staking contract tests
*/
contract PolicyManagerForStakingContractMock {

    uint32 public secondsPerPeriod = 1;
    uint256 public minRewardRate;

    function withdraw() public returns (uint256) {
        uint256 value = address(this).balance;
        require(value > 0);
        msg.sender.transfer(value);
        return value;
    }

    function setMinRewardRate(uint256 _minRewardRate) public {
        minRewardRate = _minRewardRate;
    }

    function additionalMethod(uint256 _minRewardRate) public {
        minRewardRate = _minRewardRate;
    }

    // TODO #1809
//    receive() external payable {}
    fallback() external payable {}
}


/**
* @notice Contract for staking contract tests
*/
contract WorkLockForStakingContractMock {

    uint256 public startBidDate = 1;
    uint256 public claimed;
    uint256 public depositedETH;
    uint256 public compensation;
    uint256 public refundETH;

    function bid() external payable {
        depositedETH = msg.value;
    }

    function cancelBid() external {
        uint256 value = depositedETH;
        depositedETH = 0;
        msg.sender.transfer(value);
    }

    function sendCompensation() external payable {
        compensation = msg.value;
    }

    function withdrawCompensation() external {
        uint256 value = compensation;
        compensation = 0;
        msg.sender.transfer(value);
    }

    function claim() external returns (uint256) {
        claimed += 1;
        return claimed;
    }

    function sendRefund() external payable {
        refundETH = msg.value;
    }

    function refund() external returns (uint256) {
        uint256 value = refundETH;
        refundETH = 0;
        msg.sender.transfer(value);
        return value;
    }

}


/**
* @notice Contract for staking contract tests
*/
contract StakingInterfaceMockV1 {

    address public token = address(1);
    address public escrow = address(1);

    function firstMethod() public pure {}

    function secondMethod() public pure returns (uint256) {
        return 20;
    }

}


/**
* @notice Contract for staking contract tests
*/
contract StakingInterfaceMockV2 {

    address public token = address(1);
    address public escrow = address(1);

    // TODO #1809
//    receive() external payable {}
    fallback() external payable {
        // can only use with ETH
        require(msg.value > 0);
    }

    function firstMethod(uint256) public pure {}

    function secondMethod() public pure returns (uint256) {
        return 15;
    }

    function thirdMethod() public pure {}

}


/**
* @dev Interface that could be destroyed by selfdestruct
*/
contract DestroyableStakingInterface {

    address public token = address(1);
    address public escrow = address(1);

    function method() public pure returns (uint256) {
        return 15;
    }

    function destroy() public {
        selfdestruct(msg.sender);
    }

}


/**
* @notice Simple implementation of AbstractStakingContract
*/
contract SimpleStakingContract is AbstractStakingContract, Ownable {

    /**
    * @param _router Address of the StakingInterfaceRouter contract
    */
    constructor(StakingInterfaceRouter _router) public AbstractStakingContract(_router) {}

    /**
    * @notice Withdraw available amount of tokens to owner
    * @param _value Amount of token to withdraw
    */
    function withdrawTokens(uint256 _value) public override onlyOwner {
        token.safeTransfer(msg.sender, _value);
    }

    /**
    * @notice Withdraw available ETH to the owner
    */
    function withdrawETH() public override onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        msg.sender.sendValue(balance);
    }

    /**
    * @notice Calling fallback function is allowed only for the owner
    */
    function isFallbackAllowed() public override returns (bool) {
        return msg.sender == owner();
    }

}
