pragma solidity ^0.4.23;


import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";
import "./lib/AdditionalMath.sol";
import "contracts/MinersEscrow.sol";
import "contracts/NuCypherKMSToken.sol";
import "proxy/Upgradeable.sol";


/**
* @notice Contract holds policy data and locks fees
**/
contract PolicyManager is Upgradeable {
    using SafeERC20 for NuCypherKMSToken;
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

    enum PolicyInfoField {
        Client,
        IndexOfDowntimePeriods,
        LastRefundedPeriod,
        ArrangementDisabled,
        Rate,
        StartPeriod,
        LastPeriod,
        Disabled
    }

    enum NodeInfoField {
        Reward,
        RewardRate,
        LastMinedPeriod,
        RewardDelta
    }

    struct ArrangementInfo {
        uint256 indexOfDowntimePeriods;
        uint256 lastRefundedPeriod;
        bool active;
    }

    struct Policy {
        address client;
        mapping(address => ArrangementInfo) arrangements;
        address[] nodes;

        // policy for activity periods
        uint256 rate;
        uint256 startPeriod;
        uint256 lastPeriod;
        bool disabled;
    }

    struct NodeInfo {
        uint256 reward;
        uint256 rewardRate;
        uint256 lastMinedPeriod;
        mapping (uint256 => int256) rewardDelta;
    }

    bytes20 constant RESERVED_POLICY_ID = bytes20(0);
    address constant RESERVED_NODE = 0x0;

    MinersEscrow public escrow;
    mapping (bytes20 => Policy) policies;
    mapping (address => NodeInfo) nodes;

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
    * @param _numberOfPeriods Duration of the policy in periods
    * @param _nodes Nodes that will handle policy
    **/
    function createPolicy(
        bytes20 _policyId,
        uint256 _numberOfPeriods,
        address[] _nodes
    )
        public payable
    {
        require(
            policies[_policyId].rate == 0 &&
            _numberOfPeriods != 0 &&
            msg.value > 0 &&
            msg.value % _numberOfPeriods % _nodes.length == 0 &&
            _policyId != RESERVED_POLICY_ID
        );
        Policy storage policy = policies[_policyId];
        policy.client = msg.sender;
        policy.nodes = _nodes;
        uint256 currentPeriod = escrow.getCurrentPeriod();
        policy.startPeriod = currentPeriod.add(uint(1));
        policy.lastPeriod = currentPeriod.add(_numberOfPeriods);
        uint256 feeByPeriod = msg.value.div(_numberOfPeriods).div(_nodes.length);
        policy.rate = feeByPeriod;
        uint256 endPeriod = policy.lastPeriod.add(uint(1));

        policy.nodes = _nodes;
        for (uint256 i = 0; i < _nodes.length; i++) {
            require(escrow.getLockedTokens(_nodes[i]) != 0 &&
                _nodes[i] != RESERVED_NODE);
            NodeInfo storage node = nodes[_nodes[i]];
            node.rewardDelta[policy.startPeriod] = node.rewardDelta[policy.startPeriod]
                .add(feeByPeriod);
            node.rewardDelta[endPeriod] = node.rewardDelta[endPeriod].sub(feeByPeriod);
            // TODO node should pay for this
            if (node.lastMinedPeriod == 0) {
                node.lastMinedPeriod = currentPeriod;
            }
            ArrangementInfo storage arrangement = policy.arrangements[_nodes[i]];
            arrangement.indexOfDowntimePeriods =
                uint256(escrow.getMinerInfo(MinersEscrow.MinerInfoField.DowntimeLength, _nodes[i], 0));
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
            node.rewardDelta[arrangement.lastRefundedPeriod].sub(_policy.rate);
        node.rewardDelta[_endPeriod] = node.rewardDelta[_endPeriod].add(_policy.rate);
        refundValue = refundValue.add(
            _endPeriod.sub(arrangement.lastRefundedPeriod).mul(_policy.rate));
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
    function calculateRefund(Policy storage _policy, address _node) internal returns (uint256) {
        ArrangementInfo storage arrangement = _policy.arrangements[_node];
        uint256 maxPeriod = Math.min256(escrow.getCurrentPeriod(), _policy.lastPeriod);
        uint256 minPeriod = Math.max256(_policy.startPeriod, arrangement.lastRefundedPeriod);
        uint256 downtimePeriods = 0;
        uint256 length = uint256(escrow.getMinerInfo(MinersEscrow.MinerInfoField.DowntimeLength, _node, 0));
        for (uint256 i = arrangement.indexOfDowntimePeriods; i < length; i++) {
            uint256 startPeriod =
                uint256(escrow.getMinerInfo(MinersEscrow.MinerInfoField.DowntimeStartPeriod, _node, i));
            uint256 endPeriod =
                uint256(escrow.getMinerInfo(MinersEscrow.MinerInfoField.DowntimeEndPeriod, _node, i));
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
        arrangement.indexOfDowntimePeriods = i;
        uint256 lastActivePeriod =
            uint256(escrow.getMinerInfo(MinersEscrow.MinerInfoField.LastActivePeriod, _node, 0));
        if (i == length && lastActivePeriod < maxPeriod) {
            downtimePeriods = downtimePeriods.add(
                maxPeriod.sub(Math.max256(
                    minPeriod.sub(uint(1)), lastActivePeriod)));
        }
        arrangement.lastRefundedPeriod = maxPeriod.add(uint(1));

        return _policy.rate.mul(downtimePeriods);
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
    * @notice Get information about policy
    * @param _field Field to get
    * @param _policyId Policy id
    * @param _node Address of node
    **/
    function getPolicyInfo(PolicyInfoField _field, bytes20 _policyId, address _node)
        public view returns (bytes32)
    {
        Policy storage policy = policies[_policyId];
        if (_field == PolicyInfoField.Client) {
            return bytes32(policy.client);
        } else if (_field == PolicyInfoField.Rate) {
            return bytes32(policy.rate);
        } else if (_field == PolicyInfoField.StartPeriod) {
            return bytes32(policy.startPeriod);
        } else if (_field == PolicyInfoField.LastPeriod) {
            return bytes32(policy.lastPeriod);
        } else if (_field == PolicyInfoField.Disabled) {
            return policy.disabled ? bytes32(1) : bytes32(0);
        } else if (_field == PolicyInfoField.IndexOfDowntimePeriods) {
            return bytes32(policy.arrangements[_node].indexOfDowntimePeriods);
        } else if (_field == PolicyInfoField.LastRefundedPeriod) {
            return bytes32(policy.arrangements[_node].lastRefundedPeriod);
        } else if (_field == PolicyInfoField.ArrangementDisabled) {
            return !policy.arrangements[_node].active ? bytes32(1) : bytes32(0);
        }
    }

    /**
    * @notice Get information about node
    * @param _field Field to get
    * @param _node Address of node
    * @param _period Period to get reward delta
    **/
    function getNodeInfo(NodeInfoField _field, address _node, uint256 _period)
        public view returns (bytes32)
    {
        NodeInfo storage nodeInfo = nodes[_node];
        if (_field == NodeInfoField.Reward) {
            return bytes32(nodeInfo.reward);
        } else if (_field == NodeInfoField.RewardRate) {
            return bytes32(nodeInfo.rewardRate);
        } else if (_field == NodeInfoField.LastMinedPeriod) {
            return bytes32(nodeInfo.lastMinedPeriod);
        } else if (_field == NodeInfoField.RewardDelta) {
            return bytes32(nodeInfo.rewardDelta[_period]);
        }
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(address(delegateGet(_testTarget, "escrow()")) == address(escrow));
        Policy storage policy = policies[RESERVED_POLICY_ID];
        require(address(delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.Client)), RESERVED_POLICY_ID, 0x0)) == policy.client);
        require(uint256(delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.Rate)), RESERVED_POLICY_ID, 0x0)) == policy.rate);
        require(uint256(delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.StartPeriod)), RESERVED_POLICY_ID, 0x0)) == policy.startPeriod);
        require(uint256(delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.LastPeriod)), RESERVED_POLICY_ID, 0x0)) == policy.lastPeriod);
        require((delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.Disabled)), RESERVED_POLICY_ID, 0x0) == bytes32(1)) == policy.disabled);
        require(uint256(delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.IndexOfDowntimePeriods)), RESERVED_POLICY_ID, bytes32(RESERVED_NODE))) ==
                policy.arrangements[RESERVED_NODE].indexOfDowntimePeriods);
        require(uint256(delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.LastRefundedPeriod)), RESERVED_POLICY_ID, bytes32(RESERVED_NODE))) ==
                policy.arrangements[RESERVED_NODE].lastRefundedPeriod);
        require((delegateGet(_testTarget, "getPolicyInfo(uint8,bytes20,address)",
            bytes32(uint8(PolicyInfoField.ArrangementDisabled)), RESERVED_POLICY_ID, bytes32(RESERVED_NODE)) == bytes32(1)) ==
                !policy.arrangements[RESERVED_NODE].active);
        require(uint256(delegateGet(_testTarget, "getPolicyNodesLength(bytes20)",
            RESERVED_POLICY_ID)) == policy.nodes.length);
        require(address(delegateGet(_testTarget, "getPolicyNode(bytes20,uint256)",
            RESERVED_POLICY_ID, 0)) == policy.nodes[0]);
        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        require(uint256(delegateGet(_testTarget, "getNodeInfo(uint8,address,uint256)",
            bytes32(uint8(NodeInfoField.Reward)), bytes32(RESERVED_NODE), 0)) == nodeInfo.reward);
        require(uint256(delegateGet(_testTarget, "getNodeInfo(uint8,address,uint256)",
            bytes32(uint8(NodeInfoField.RewardRate)), bytes32(RESERVED_NODE), 0)) == nodeInfo.rewardRate);
        require(uint256(delegateGet(_testTarget, "getNodeInfo(uint8,address,uint256)",
            bytes32(uint8(NodeInfoField.LastMinedPeriod)), bytes32(RESERVED_NODE), 0)) == nodeInfo.lastMinedPeriod);
        require(int256(delegateGet(_testTarget, "getNodeInfo(uint8,address,uint256)",
            bytes32(uint8(NodeInfoField.RewardDelta)), bytes32(RESERVED_NODE), 11)) == nodeInfo.rewardDelta[11]);
    }

    function finishUpgrade(address _target) public onlyOwner {
        PolicyManager policyManager = PolicyManager(_target);
        escrow = policyManager.escrow();
        // Create fake Policy and NodeInfo to use them in verifyState(address)
        Policy storage policy = policies[RESERVED_POLICY_ID];
        policy.client = owner;
        policy.startPeriod = 1;
        policy.lastPeriod = 2;
        policy.rate = 3;
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
    }
}