pragma solidity ^0.4.24;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";
import "proxy/Government.sol";


/**
* @notice Contract that can call library contract
**/
contract Caller {
    /**
    * @notice Target contract address
    **/
    function target() public returns (address);
}


/**
* @notice Proxy interface to access main contracts from the UserEscrow contract
* @dev All methods must be stateless because this code will execute by delegatecall call
* If state is needed - use getStateAddress() method to access state of this contract
**/
contract UserEscrowProxyInterface {

    event DepositedAsMiner(address indexed owner, uint256 value, uint16 periods);
    event WithdrawnAsMiner(address indexed owner, uint256 value);
    event Locked(address indexed owner, uint256 value, uint16 periods);
    event Divided(address indexed owner, uint256 index, uint256 newValue, uint16 periods);
    event ActivityConfirmed(address indexed owner);
    event Mined(address indexed owner);
    event RewardWithdrawnAsMiner(address indexed owner, uint256 value);
    event MinRewardRateSet(address indexed owner, uint256 value);
    event Voted(address indexed owner, bool voteFor);

    NuCypherToken public token;
    MinersEscrow public escrow;
    PolicyManager public policyManager;
    Government public government;

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    * @param _government Government contract
    **/
    constructor(
        NuCypherToken _token,
        MinersEscrow _escrow,
        PolicyManager _policyManager,
        Government _government
    )
        public
    {
        require(address(_token) != 0x0 &&
            address(_escrow) != 0x0 &&
            address(_policyManager) != 0x0 &&
            address(_government) != 0x0);
        token = _token;
        escrow = _escrow;
        policyManager = _policyManager;
        government = _government;
    }

    // TODO maybe restrict use ETH in the user escrow (remove)?
    function () public payable {}

    /**
    * @notice Get contract which stores state
    * @dev Assume that caller has target() method
    **/
    function getStateContract() internal returns (UserEscrowProxyInterface) {
        return UserEscrowProxyInterface(Caller(Caller(address(this)).target()).target());
    }

    /**
    * @notice Deposit tokens to the miners escrow
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    // TODO rename?
    function minerDeposit(uint256 _value, uint16 _periods) public {
        UserEscrowProxyInterface state = getStateContract();
        NuCypherToken tokenFromState = state.token();
        require(tokenFromState.balanceOf(address(this)) > _value);
        MinersEscrow escrowFromState = state.escrow();
        tokenFromState.approve(address(escrowFromState), _value);
        escrowFromState.deposit(_value, _periods);
        emit DepositedAsMiner(msg.sender, _value, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens from the miners escrow to the user escrow
    * @param _value Amount of token to withdraw
    **/
    // TODO rename?
    function minerWithdraw(uint256 _value) public {
        getStateContract().escrow().withdraw(_value);
        emit WithdrawnAsMiner(msg.sender, _value);
    }

    /**
    * @notice Lock some tokens or increase lock in the miners escrow
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint16 _periods) public {
        getStateContract().escrow().lock(_value, _periods);
        emit Locked(msg.sender, _value, _periods);
    }

    /**
    * @notice Divide stake into two parts
    * @param _index Index of stake
    * @param _newValue New stake value
    * @param _periods Amount of periods for extending stake
    **/
    function divideStake(
        uint256 _index,
        uint256 _newValue,
        uint16 _periods
    )
        public
    {
        getStateContract().escrow().divideStake(_index, _newValue, _periods);
        emit Divided(msg.sender, _index, _newValue, _periods);
    }

    /**
    * @notice Confirm activity for future period in the miners escrow
    **/
    function confirmActivity() external {
        getStateContract().escrow().confirmActivity();
        emit ActivityConfirmed(msg.sender);
    }

    /**
    * @notice Mint tokens in the miners escrow
    **/
    function mint() external {
        getStateContract().escrow().mint();
        emit Mined(msg.sender);
    }

    /**
    * @notice Withdraw available reward from the policy manager to the user escrow
    **/
    function policyRewardWithdraw() public {
        uint256 balance = address(this).balance;
        uint256 value = getStateContract().policyManager().withdraw(msg.sender);
        emit RewardWithdrawnAsMiner(msg.sender, value);
    }

    /**
    * @notice Set the minimum reward that the miner will take in the policy manager
    **/
    function setMinRewardRate(uint256 _minRewardRate) public {
        getStateContract().policyManager().setMinRewardRate(_minRewardRate);
        emit MinRewardRateSet(msg.sender, _minRewardRate);
    }

    /**
    * @notice Vote for the upgrade in the government contract
    **/
    function vote(bool _voteFor) public {
        getStateContract().government().vote(_voteFor);
        emit Voted(msg.sender, _voteFor);
    }

}
