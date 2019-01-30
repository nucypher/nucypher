pragma solidity ^0.5.3;


import "./UserEscrow.sol";
import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";


/**
* @notice Proxy to access main contracts from the UserEscrow contract
* @dev All methods must be stateless because this code will execute by delegatecall call
* If state is needed - use getStateContract() method to access state of this contract
**/
contract UserEscrowProxy {

    event DepositedAsMiner(address indexed owner, uint256 value, uint16 periods);
    event WithdrawnAsMiner(address indexed owner, uint256 value);
    event Locked(address indexed owner, uint256 value, uint16 periods);
    event Divided(address indexed owner, uint256 index, uint256 newValue, uint16 periods);
    event ActivityConfirmed(address indexed owner);
    event Mined(address indexed owner);
    event PolicyRewardWithdrawn(address indexed owner, uint256 value);
    event MinRewardRateSet(address indexed owner, uint256 value);

    NuCypherToken public token;
    MinersEscrow public escrow;
    PolicyManager public policyManager;

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    **/
    constructor(
        NuCypherToken _token,
        MinersEscrow _escrow,
        PolicyManager _policyManager
    )
        public
    {
        require(address(_token) != address(0) &&
            address(_escrow) != address(0) &&
            address(_policyManager) != address(0));
        token = _token;
        escrow = _escrow;
        policyManager = _policyManager;
    }

    /**
    * @notice Get contract which stores state
    * @dev Assume that `this` is the UserEscrow contract
    **/
    function getStateContract() internal view returns (UserEscrowProxy) {
        address payable userEscrowAddress = address(bytes20(address(this)));
        UserEscrowLibraryLinker linker = UserEscrow(userEscrowAddress).linker();
        return UserEscrowProxy(linker.target());
    }

    /**
    * @notice Deposit tokens to the miners escrow
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function depositAsMiner(uint256 _value, uint16 _periods) public {
        UserEscrowProxy state = getStateContract();
        NuCypherToken tokenFromState = state.token();
        require(tokenFromState.balanceOf(address(this)) >= _value);
        MinersEscrow escrowFromState = state.escrow();
        tokenFromState.approve(address(escrowFromState), _value);
        escrowFromState.deposit(_value, _periods);
        emit DepositedAsMiner(msg.sender, _value, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens from the miners escrow to the user escrow
    * @param _value Amount of token to withdraw
    **/
    function withdrawAsMiner(uint256 _value) public {
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
    function withdrawPolicyReward() public {
        uint256 value = getStateContract().policyManager().withdraw(msg.sender);
        emit PolicyRewardWithdrawn(msg.sender, value);
    }

    /**
    * @notice Set the minimum reward that the miner will take in the policy manager
    **/
    function setMinRewardRate(uint256 _minRewardRate) public {
        getStateContract().policyManager().setMinRewardRate(_minRewardRate);
        emit MinRewardRateSet(msg.sender, _minRewardRate);
    }

}
