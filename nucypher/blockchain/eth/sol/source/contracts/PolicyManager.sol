pragma solidity ^0.4.23;


import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";
import "./lib/AdditionalMath.sol";
import "contracts/MinersEscrow.sol";
import "contracts/NuCypherToken.sol";
import "proxy/Upgradeable.sol";


/**
* @notice Contract holds policy data and locks fees
**/
contract PolicyManager is Upgradeable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;
    using AdditionalMath for uint256;
    using AdditionalMath for int256;

    event PolicyCreated(
        bytes20 indexed policyId,
        address indexed client,
        address[] indexed nodes
    );
    event PolicyRevoked(
        bytes20 indexed policyId,
        address indexed client,
        uint256 value
    );
    event ArrangementRevoked(
        bytes20 indexed policyId,
        address indexed client,
        address indexed node,
        uint256 value
    );
    event Withdrawn(address indexed node, uint256 value);
    event RefundForArrangement(
        bytes20 indexed policyId,
        address indexed client,
        address indexed node,
        uint256 value
    );
    event RefundForPolicy(
        bytes20 indexed policyId,
        address indexed client,
        uint256 value
    );

    struct ArrangementInfo {
        uint256 indexOfDowntimePeriods;
        uint256 lastRefundedPeriod;
        bool active;
    }

    struct Policy {
        address client;

        // policy for activity periods
        uint256 rewardRate;
        uint256 firstReward;
        uint256 startPeriod;
        uint256 lastPeriod;
        bool disabled;

        mapping(address => ArrangementInfo) arrangements;
        address[] nodes;
    }

    struct NodeInfo {
        uint256 reward;
        uint256 rewardRate;
        uint256 lastMinedPeriod;
        mapping (uint256 => int256) rewardDelta;
        uint256 minRewardRate;
    }

    bytes20 constant RESERVED_POLICY_ID = bytes20(0);
    address constant RESERVED_NODE = 0x0;

    MinersEscrow public escrow;
    mapping (bytes20 => Policy) public policies;
    mapping (address => NodeInfo) public nodes;

    /**
    * @notice Constructor sets address of the escrow contract
    * @param _escrow Escrow contract
    **/
    constructor(MinersEscrow _escrow) public {
        require(address(_escrow) != 0x0);
        escrow = _escrow;
    }

    /**
    * @notice Create policy by client
    * @dev Generate policy id before creation
    * @param _policyId Policy id
    * @param _numberOfPeriods Duration of the policy in periods except first period
    * @param _firstReward Reward for first period
    * @param _nodes Nodes that will handle policy
    **/
    function createPolicy(
        bytes20 _policyId,
        uint256 _numberOfPeriods,
        uint256 _firstReward,
        address[] _nodes
    )
        public payable
    {
        require(
            _policyId != RESERVED_POLICY_ID &&
            policies[_policyId].rewardRate == 0 &&
            _numberOfPeriods != 0 &&
            msg.value > 0
        );
        Policy storage policy = policies[_policyId];
        policy.client = msg.sender;
        policy.nodes = _nodes;
        uint256 currentPeriod = escrow.getCurrentPeriod();
        policy.startPeriod = currentPeriod.add(uint(1));
        policy.lastPeriod = currentPeriod.add(_numberOfPeriods);
        policy.rewardRate = msg.value.div(_nodes.length).sub(_firstReward).div(_numberOfPeriods);
        policy.firstReward = _firstReward;
        require(policy.rewardRate > _firstReward &&
            (_firstReward + policy.rewardRate * _numberOfPeriods) * _nodes.length  == msg.value);
        uint256 endPeriod = policy.lastPeriod.add(uint(1));
        uint256 startReward = policy.rewardRate - _firstReward;

        policy.nodes = _nodes;
        for (uint256 i = 0; i < _nodes.length; i++) {
            address node = _nodes[i];
            require(escrow.getLockedTokens(node) != 0 && node != RESERVED_NODE);
            NodeInfo storage nodeInfo = nodes[node];
            require(policy.rewardRate >= nodeInfo.minRewardRate);
            nodeInfo.rewardDelta[currentPeriod] = nodeInfo.rewardDelta[currentPeriod].add(_firstReward);
            nodeInfo.rewardDelta[policy.startPeriod] = nodeInfo.rewardDelta[policy.startPeriod]
                .add(startReward);
            nodeInfo.rewardDelta[endPeriod] = nodeInfo.rewardDelta[endPeriod].sub(policy.rewardRate);
            // TODO node should pay for this
            if (nodeInfo.lastMinedPeriod == 0) {
                nodeInfo.lastMinedPeriod = currentPeriod.sub(uint256(1));
            }
            ArrangementInfo storage arrangement = policy.arrangements[node];
            arrangement.indexOfDowntimePeriods = escrow.getDowntimeLength(node);
            arrangement.active = true;
        }

        emit PolicyCreated(_policyId, msg.sender, _nodes);
    }

    /**
    * @notice Update node reward
    * @param _node Node address
    * @param _period Processed period
    **/
    function updateReward(address _node, uint256 _period) external {
        require(msg.sender == address(escrow));
        NodeInfo storage node = nodes[_node];
        if (node.lastMinedPeriod == 0 || _period <= node.lastMinedPeriod) {
            return;
        }
        for (uint256 i = node.lastMinedPeriod + 1; i <= _period; i++) {
            node.rewardRate = node.rewardRate.add(node.rewardDelta[i]);
//            delete node.rewardDelta[i];
        }
        node.lastMinedPeriod = _period;
        node.reward = node.reward.add(node.rewardRate);
    }

    /**
    * @notice Withdraw reward by node
    **/
    function withdraw() public {
        NodeInfo storage node = nodes[msg.sender];
        uint256 reward = node.reward;
        require(reward != 0);
        node.reward = 0;
        msg.sender.transfer(reward);
        emit Withdrawn(msg.sender, reward);
    }

    /**
    * @notice Revoke policy by client
    * @param _policyId Policy id
    **/
    function revokePolicy(bytes20 _policyId) public {
        Policy storage policy = policies[_policyId];
        require(policy.client == msg.sender && !policy.disabled);
        uint256 refundValue = 0;
        uint256 endPeriod = policy.lastPeriod.add(uint(1));
        for (uint256 i = 0; i < policy.nodes.length; i++) {
            address node = policy.nodes[i];
            if (!policy.arrangements[node].active) {
                continue;
            }
            uint256 nodeRefundValue = revokeArrangement(policy, node, endPeriod);
            refundValue = refundValue.add(nodeRefundValue);
            emit ArrangementRevoked(_policyId, msg.sender, node, nodeRefundValue);
        }
        policy.disabled = true;
        if (refundValue > 0) {
            msg.sender.transfer(refundValue);
        }
        emit PolicyRevoked(_policyId, msg.sender, refundValue);
    }

    /**
    * @notice Revoke arrangement by client
    * @param _policyId Policy id
    * @param _node Node that will be excluded
    **/
    function revokeArrangement(bytes20 _policyId, address _node)
        public returns (uint256 refundValue)
    {
        Policy storage policy = policies[_policyId];
        require(policy.client == msg.sender &&
            !policy.disabled &&
            policy.arrangements[_node].active);
        uint256 endPeriod = policy.lastPeriod.add(uint(1));
        refundValue = revokeArrangement(policy, _node, endPeriod);
        if (refundValue > 0) {
            msg.sender.transfer(refundValue);
        }
        emit ArrangementRevoked(_policyId, msg.sender, _node, refundValue);
    }

    /**
    * @notice Revoke arrangement by client
    * @param _policy Policy
    * @param _node Node that will be excluded
    * @param _endPeriod Pre-calculated end of period value
    **/
    function revokeArrangement(Policy storage _policy, address _node, uint256 _endPeriod)
        internal returns (uint256 refundValue)
    {
        refundValue = calculateRefund(_policy, _node);
        NodeInfo storage node = nodes[_node];
        ArrangementInfo storage arrangement = _policy.arrangements[_node];
        node.rewardDelta[arrangement.lastRefundedPeriod] =
            node.rewardDelta[arrangement.lastRefundedPeriod].sub(_policy.rewardRate);
        node.rewardDelta[_endPeriod] = node.rewardDelta[_endPeriod].add(_policy.rewardRate);
        refundValue = refundValue.add(
            _endPeriod.sub(arrangement.lastRefundedPeriod).mul(_policy.rewardRate));
        _policy.arrangements[_node].active = false;
    }

    /**
    * @notice Refund part of fee by client
    * @param _policyId Policy id
    **/
    function refund(bytes20 _policyId) public {
        Policy storage policy = policies[_policyId];
        require(msg.sender == policy.client && !policy.disabled);
        uint256 refundValue = 0;
        uint256 numberOfActive = policy.nodes.length;
        for (uint256 i = 0; i < policy.nodes.length; i++) {
            address node = policy.nodes[i];
            if (!policy.arrangements[node].active) {
                numberOfActive--;
                continue;
            }
            uint256 nodeRefundValue = calculateRefund(policy, node);
            if (policy.arrangements[node].lastRefundedPeriod > policy.lastPeriod) {
                policy.arrangements[node].active = false;
                numberOfActive--;
            }
            refundValue = refundValue.add(nodeRefundValue);
            emit RefundForArrangement(_policyId, msg.sender, node, nodeRefundValue);
        }
        if (refundValue > 0) {
            msg.sender.transfer(refundValue);
        }
        if (numberOfActive == 0) {
            policy.disabled = true;
        }
        emit RefundForPolicy(_policyId, msg.sender, refundValue);
    }

    /**
    * @notice Refund part of one node's fee by client
    * @param _policyId Policy id
    * @param _node Node address
    **/
    function refund(bytes20 _policyId, address _node)
        public returns (uint256 refundValue)
    {
        Policy storage policy = policies[_policyId];
        require(msg.sender == policy.client &&
            !policy.disabled &&
            policy.arrangements[_node].active);
        refundValue = calculateRefund(policy, _node);
        if (policy.arrangements[_node].lastRefundedPeriod > policy.lastPeriod) {
            policy.arrangements[_node].active = false;
        }
        if (refundValue > 0) {
            msg.sender.transfer(refundValue);
        }
        emit RefundForArrangement(_policyId, msg.sender, _node, refundValue);
    }

    /**
    * @notice Calculate amount of refund
    * @param _policy Policy
    * @param _node Node for calculation
    **/
    //TODO extract checkRefund method
    function calculateRefund(Policy storage _policy, address _node) internal returns (uint256 refundValue) {
        ArrangementInfo storage arrangement = _policy.arrangements[_node];
        uint256 maxPeriod = Math.min256(escrow.getCurrentPeriod(), _policy.lastPeriod);
        uint256 minPeriod = Math.max256(_policy.startPeriod, arrangement.lastRefundedPeriod);
        uint256 downtimePeriods = 0;
        uint256 length = escrow.getDowntimeLength(_node);
        for (uint256 i = arrangement.indexOfDowntimePeriods; i < length; i++) {
            uint256 startPeriod;
            uint256 endPeriod;
            (startPeriod, endPeriod) = escrow.getDowntime(_node, i);
            if (startPeriod > maxPeriod) {
                break;
            } else if (endPeriod < minPeriod) {
                continue;
            }
            downtimePeriods = downtimePeriods.add(
                Math.min256(maxPeriod, endPeriod)
                .sub(Math.max256(minPeriod, startPeriod))
                .add(uint(1)));
            if (maxPeriod <= endPeriod) {
                break;
            }
        }

        uint256 lastActivePeriod;
        (,,,,lastActivePeriod) = escrow.minerInfo(_node);
        if (i == length && lastActivePeriod < maxPeriod) {
            downtimePeriods = downtimePeriods.add(
                maxPeriod.sub(Math.max256(
                    minPeriod.sub(uint(1)), lastActivePeriod)));
        }

        // TODO refactor
        if (arrangement.lastRefundedPeriod == 0) {
            if (lastActivePeriod < _policy.startPeriod - 1) {
                refundValue = _policy.firstReward;
            } else if (arrangement.indexOfDowntimePeriods < length) {
                (startPeriod, endPeriod) = escrow.getDowntime(_node, arrangement.indexOfDowntimePeriods);
                if (_policy.startPeriod > startPeriod && _policy.startPeriod - 1 <= endPeriod) {
                    refundValue = _policy.firstReward;
                }
            }
        }
        refundValue = refundValue.add(_policy.rewardRate.mul(downtimePeriods));

        arrangement.indexOfDowntimePeriods = i;
        arrangement.lastRefundedPeriod = maxPeriod.add(uint(1));
    }

    /**
    * @notice Set the minimum reward that the node will take
    **/
    function setMinRewardRate(uint256 _minRewardRate) public {
        NodeInfo storage node = nodes[msg.sender];
        node.minRewardRate = _minRewardRate;
    }

    /**
    * @notice Get number of nodes in policy
    * @param _policyId Policy id
    **/
    function getPolicyNodesLength(bytes20 _policyId)
        public view returns (uint256)
    {
        return policies[_policyId].nodes.length;
    }

    /**
    * @notice Get node from policy
    * @param _policyId Policy id
    * @param _index Index of node
    **/
    function getPolicyNode(bytes20 _policyId, uint256 _index)
        public view returns (address)
    {
        return policies[_policyId].nodes[_index];
    }

    /**
    * @notice Get information about node reward
    * @param _node Address of node
    * @param _period Period to get reward delta
    **/
    function getNodeRewardDelta(address _node, uint256 _period)
        public view returns (int256)
    {
        return nodes[_node].rewardDelta[_period];
    }

    /**
    * @notice Return the information about arrangement
    **/
    function getArrangementInfo(bytes20 _policyId, address _node)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (ArrangementInfo)
        public view returns (uint256 indexOfDowntimePeriods, uint256 lastRefundedPeriod, bool active)
    {
        ArrangementInfo storage info = policies[_policyId].arrangements[_node];
        indexOfDowntimePeriods = info.indexOfDowntimePeriods;
        lastRefundedPeriod = info.lastRefundedPeriod;
        active = info.active;
    }


    /**
    * @dev Get Policy structure by delegatecall
    **/
    function delegateGetPolicy(address _target, bytes20 _policyId)
        internal returns (Policy memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, "policies(bytes20)", 1, bytes32(_policyId), 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get ArrangementInfo structure by delegatecall
    **/
    function delegateGetArrangementInfo(address _target, bytes20 _policyId, address _node)
        internal returns (ArrangementInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getArrangementInfo(bytes20,address)", 2, bytes32(_policyId), bytes32(_node));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get NodeInfo structure by delegatecall
    **/
    function delegateGetNodeInfo(address _target, address _node)
        internal returns (NodeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, "nodes(address)", 1, bytes32(_node), 0);
        assembly {
            result := memoryAddress
        }
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(address(delegateGet(_testTarget, "escrow()")) == address(escrow));
        Policy storage policy = policies[RESERVED_POLICY_ID];
        Policy memory policyToCheck = delegateGetPolicy(_testTarget, RESERVED_POLICY_ID);
        require(policyToCheck.client == policy.client &&
            policyToCheck.rewardRate == policy.rewardRate &&
            policyToCheck.firstReward == policy.firstReward &&
            policyToCheck.startPeriod == policy.startPeriod &&
            policyToCheck.lastPeriod == policy.lastPeriod &&
            policyToCheck.disabled == policy.disabled);

        ArrangementInfo storage arrangement = policy.arrangements[RESERVED_NODE];
        ArrangementInfo memory arrangementToCheck = delegateGetArrangementInfo(
            _testTarget, RESERVED_POLICY_ID, RESERVED_NODE);
        require(arrangementToCheck.indexOfDowntimePeriods == arrangement.indexOfDowntimePeriods &&
            arrangementToCheck.lastRefundedPeriod == arrangement.lastRefundedPeriod &&
            arrangementToCheck.active == arrangement.active);

        require(uint256(delegateGet(_testTarget, "getPolicyNodesLength(bytes20)",
            RESERVED_POLICY_ID)) == policy.nodes.length);
        require(address(delegateGet(_testTarget, "getPolicyNode(bytes20,uint256)",
            RESERVED_POLICY_ID, 0)) == policy.nodes[0]);

        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        NodeInfo memory nodeInfoToCheck = delegateGetNodeInfo(_testTarget, RESERVED_NODE);
        require(nodeInfoToCheck.reward == nodeInfo.reward &&
            nodeInfoToCheck.rewardRate == nodeInfo.rewardRate &&
            nodeInfoToCheck.lastMinedPeriod == nodeInfo.lastMinedPeriod &&
            nodeInfoToCheck.minRewardRate == nodeInfo.minRewardRate);

        require(int256(delegateGet(_testTarget, "getNodeRewardDelta(address,uint256)",
            bytes32(RESERVED_NODE), 11)) == nodeInfo.rewardDelta[11]);
    }

    function finishUpgrade(address _target) public onlyOwner {
        PolicyManager policyManager = PolicyManager(_target);
        escrow = policyManager.escrow();
        // Create fake Policy and NodeInfo to use them in verifyState(address)
        Policy storage policy = policies[RESERVED_POLICY_ID];
        policy.client = owner;
        policy.startPeriod = 1;
        policy.lastPeriod = 2;
        policy.rewardRate = 3;
        policy.firstReward = 4;
        policy.disabled = true;
        policy.nodes.push(RESERVED_NODE);
        policy.arrangements[RESERVED_NODE].indexOfDowntimePeriods = 11;
        policy.arrangements[RESERVED_NODE].lastRefundedPeriod = 22;
        policy.arrangements[RESERVED_NODE].active = true;
        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        nodeInfo.reward = 100;
        nodeInfo.rewardRate = 33;
        nodeInfo.lastMinedPeriod = 44;
        nodeInfo.rewardDelta[11] = 55;
        nodeInfo.minRewardRate = 777;
    }
}