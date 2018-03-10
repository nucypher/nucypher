pragma solidity ^0.4.18;


import "./zeppelin/token/ERC20/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
import "./zeppelin/math/Math.sol";
import "./lib/AdditionalMath.sol";
import "./MinersEscrow.sol";
import "./NuCypherKMSToken.sol";


/**
* @notice Contract holds policy data and locks fees
**/
contract PolicyManager {
    using SafeERC20 for NuCypherKMSToken;
    using SafeMath for uint256;
    using AdditionalMath for uint256;
    using AdditionalMath for int256;

    event PolicyCreated(
        bytes20 indexed policyId,
        address indexed client,
        address indexed node
    );
    event PolicyRevoked(bytes20 indexed policyId);
    event Withdrawn(
        address indexed node,
        uint256 value
    );
    event Refunded(
        bytes20 indexed policyId,
        address indexed client,
        uint256 value
    );

    struct Policy {
        address client;
        address node;

        // policy for activity periods
        uint256 rate;
        uint256 startPeriod;
        uint256 lastPeriod;
        uint256 indexOfDowntimePeriods;
    }

    struct NodeInfo {
        uint256 reward;
        uint256 lastRewardByPeriod;
        uint256 lastRewardedPeriod;
        mapping (uint256 => int256) rewardChanges;
    }

    MinersEscrow public escrow;
    mapping (bytes20 => Policy) public policies;
    mapping (address => NodeInfo) public nodes;

    /**
    * @notice Constructor sets address of the escrow contract
    * @param _escrow Escrow contract
    **/
    function PolicyManager(
        MinersEscrow _escrow
    )
        public
    {
        require(address(_escrow) != 0x0);
        escrow = _escrow;
    }

    /**
    * @notice Create policy by client
    * @dev Generate policy id before creation
    * @param _policyId Policy id
    * @param _node Node that will handle policy
    * @param _numberOfPeriods Duration of the policy in periods
    **/
    function createPolicy(
        bytes20 _policyId,
        address _node,
        uint256 _numberOfPeriods
    )
        public payable
    {
        require(
            policies[_policyId].rate == 0 &&
            _numberOfPeriods != 0 &&
            escrow.getLockedTokens(_node) != 0 &&
            msg.value > 0 &&
            msg.value % _numberOfPeriods == 0
        );
        Policy storage policy = policies[_policyId];
        policy.client = msg.sender;
        policy.node = _node;
        uint256 currentPeriod = escrow.getCurrentPeriod();
        policy.startPeriod = currentPeriod.add(uint(1));
        policy.lastPeriod = currentPeriod.add(_numberOfPeriods);
        uint256 feeByPeriod = msg.value.div(_numberOfPeriods);
        policy.rate = feeByPeriod;

        NodeInfo storage node = nodes[_node];
        uint256 endPeriod = policy.lastPeriod.add(uint(1));
        node.rewardChanges[policy.startPeriod] = node.rewardChanges[policy.startPeriod]
            .add(feeByPeriod);
        node.rewardChanges[endPeriod] = node.rewardChanges[endPeriod].sub(feeByPeriod);
        // TODO node should pay for this
        if (node.lastRewardedPeriod == 0) {
            node.lastRewardedPeriod = currentPeriod;
        }

        policy.indexOfDowntimePeriods = escrow.getDowntimePeriodsLength(_node);
        PolicyCreated(_policyId, msg.sender, _node);
    }

    /**
    * @notice Update node reward
    * @param _node Node address
    * @param _period Processed period
    **/
    function updateReward(address _node, uint256 _period) external {
        require(msg.sender == address(escrow));
        NodeInfo storage node = nodes[_node];
        if (node.lastRewardedPeriod == 0) {
            return;
        }
        for (uint256 i = node.lastRewardedPeriod + 1; i <= _period; i++) {
            node.lastRewardByPeriod = node.lastRewardByPeriod.add(node.rewardChanges[i]);
//            delete node.rewardChanges[i];
        }
        node.lastRewardedPeriod = _period;
        node.reward = node.reward.add(node.lastRewardByPeriod);
    }

    /**
    * @notice Withdraw fee by node
    **/
    function withdraw() public {
        NodeInfo storage node = nodes[msg.sender];
        uint256 reward = node.reward;
        require(reward != 0);
        node.reward = 0;
        msg.sender.transfer(reward);
        Withdrawn(msg.sender, reward);
    }

    /**
    * @notice Revoke policy by client
    * @param _policyId Policy id
    **/
    function revokePolicy(bytes20 _policyId) public {
        Policy storage policy = policies[_policyId];
        require(policy.client == msg.sender);
        uint256 refund = calculateRefund(_policyId);
        NodeInfo storage node = nodes[policy.node];
        uint256 endPeriod = policy.lastPeriod.add(uint(1));
        node.rewardChanges[policy.startPeriod] = node.rewardChanges[policy.startPeriod]
            .sub(policy.rate);
        node.rewardChanges[endPeriod] = node.rewardChanges[endPeriod].add(policy.rate);
        refund = refund.add(endPeriod.sub(policy.startPeriod).mul(policy.rate));
        delete policies[_policyId];
        if (refund > 0) {
            msg.sender.transfer(refund);
            Refunded(_policyId, msg.sender, refund);
        }
        PolicyRevoked(_policyId);
    }

    /**
    * @notice Refund part of fee by client
    * @param _policyId Policy id
    **/
    function refund(bytes20 _policyId) public {
        Policy storage policy = policies[_policyId];
        require(msg.sender == policy.client);
        uint256 refundValue = calculateRefund(_policyId);
        address client = policy.client;
        if (policy.startPeriod > policy.lastPeriod) {
            delete policies[_policyId];
        }
        if (refundValue > 0) {
            client.transfer(refundValue);
            Refunded(_policyId, client, refundValue);
        }
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    **/
    //TODO extract checkRefund method
    function calculateRefund(bytes20 _policyId) internal returns (uint256) {
        Policy storage policy = policies[_policyId];
        uint256 currentPeriod = escrow.getCurrentPeriod();
        uint256 maxPeriod = Math.min256(currentPeriod, policy.lastPeriod);
        uint256 minPeriod = policy.startPeriod;
        uint256 downtimePeriods = 0;
        uint256 length = escrow.getDowntimePeriodsLength(policy.node);
        for (uint256 i = policy.indexOfDowntimePeriods; i < length; i++) {
            uint256 startPeriod;
            uint256 endPeriod;
            (startPeriod, endPeriod) = escrow.getDowntimePeriods(policy.node, i);
            if (startPeriod > maxPeriod) {
                break;
            } else if (endPeriod < minPeriod) {
                continue;
            }
            uint256 max = Math.min256(maxPeriod, endPeriod);
            uint256 min = Math.max256(minPeriod, startPeriod);
            downtimePeriods = downtimePeriods.add(max.sub(min).add(uint(1)));
            if (maxPeriod <= endPeriod) {
                break;
            }
        }
        policy.indexOfDowntimePeriods = i;
        uint256 lastActivePeriod = escrow.getLastActivePeriod(policy.node);
        if (i == length && lastActivePeriod < maxPeriod) {
            min = Math.max256(minPeriod.sub(uint(1)), lastActivePeriod);
            downtimePeriods = downtimePeriods.add(maxPeriod.sub(min));
        }
        policy.startPeriod = maxPeriod.add(uint(1));

        return policy.rate.mul(downtimePeriods);
    }

}
