pragma solidity ^0.4.0;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
import "./Escrow.sol";
import "./NuCypherKMSToken.sol";


/**
* @notice Contract holds policy data and locks fees
**/
contract PolicyManager {
    using SafeERC20 for NuCypherKMSToken;
    using SafeMath for uint256;

    enum PolicyState { Pending, Active }

    struct Policy {
        address client;
        address node;
        uint256 fee;
//        uint256 lockedFee;
        PolicyState state;
        uint256 numberOfPeriods;
        uint256 lastPeriod;
    }

    NuCypherKMSToken token;
    Escrow escrow;
    mapping (bytes20 => Policy) policies;
//    mapping (address => byte20[]) nodePolicies;
//    mapping (address => byte20[]) clientPolicies;

    /**
    * @notice The PolicyManager constructor sets addresses of token and escrow contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    **/
    function PolicyManager(
        NuCypherKMSToken _token,
        Escrow _escrow
    ) {
        require(address(_token) != 0x0);
        token = _token;
        escrow = _escrow;
    }

    /**
    * @notice Create policy by client
    * @dev Generate policy id before creation
    * @param _policyId Policy id
    * @param _fee Amount of node reward
    * @param _node Node that will handle policy
    * @param _numberOfPeriods Duration of the policy in periods
    **/
    function createPolicy(
        bytes20 _policyId,
        uint256 _fee,
        address _node,
        uint256 _numberOfPeriods
    )
        public
    {
        require(
            policies[_policyId].fee == 0 &&
            _fee != 0 &&
            _numberOfPeriods != 0 &&
            escrow.getLockedTokens(_node) != 0
        );
        token.safeTransferFrom(msg.sender, address(this), _fee);
        var policy = policies[_policyId];
        policy.client = msg.sender;
        policy.node = _node;
        policy.fee = _fee;
//        policy.lockedFee = _fee;
        policy.state = PolicyState.Pending;
        policy.numberOfPeriods = _numberOfPeriods;
    }

    /**
    * @notice Revoke policy by client (all states) or node (only Pending state)
    * @param _policyId Policy id
    **/
    function revokePolicy(bytes20 _policyId) public  {
        var policy = policies[_policyId];
        require(policy.state == PolicyState.Pending &&
            policy.client == msg.sender);
        var fee = policy.fee;
        var client = policy.client;
        delete policies[_policyId];
        token.safeTransfer(client, fee);
    }

    /**
    * @notice Confirm policy by node
    * @param _policyId Policy id
    **/
    function confirmPolicy(bytes20 _policyId) public {
        var policy = policies[_policyId];
        require(policy.state == PolicyState.Pending &&
            policy.node == msg.sender);
        policy.state = PolicyState.Active;
        policy.lastPeriod = escrow.getCurrentPeriod()
            .add(policy.numberOfPeriods);
    }

    /**
    * @notice Finish policy and withdraw fee by node
    * @param _policyId Policy id
    **/
    function finishPolicy(bytes20 _policyId) public {
        var policy = policies[_policyId];
        require(policy.state == PolicyState.Active &&
            policy.node == msg.sender &&
            escrow.getCurrentPeriod() > policy.lastPeriod);
        var fee = policy.fee;
        var node = policy.client;
        delete policies[_policyId];
        token.safeTransfer(node, fee);
    }

}
