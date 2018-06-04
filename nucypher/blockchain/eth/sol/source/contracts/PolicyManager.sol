pragma solidity ^0.4.24;


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
        address node;
        uint256 indexOfDowntimePeriods;
        uint256 lastRefundedPeriod;
    }

    struct Policy {
        address client;

        // policy for activity periods
        uint256 rewardRate;
        uint256 firstReward;
        uint256 startPeriod;
        uint256 lastPeriod;
        bool disabled;

        ArrangementInfo[] arrangements;
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
    uint256 public secondsPerPeriod;
    mapping (bytes20 => Policy) public policies;
    mapping (address => NodeInfo) public nodes;

    /**
    * @notice Constructor sets address of the escrow contract
    * @param _escrow Escrow contract
    **/
    constructor(MinersEscrow _escrow) public {
        require(address(_escrow) != 0x0);
        escrow = _escrow;
        secondsPerPeriod = escrow.secondsPerPeriod();
    }

    /**
    * @dev Checks that sender is the MinersEscrow contract
    **/
    modifier onlyEscrowContract()
    {
        require(msg.sender == address(escrow));
        _;
    }

    /**
    * @return Number of current period
    **/
    function getCurrentPeriod() public view returns (uint256) {
        return block.timestamp / secondsPerPeriod;
    }

    /**
    * @notice Register a node
    * @param _node Node address
    * @param _period Initial period
    **/
    function register(address _node, uint256 _period) external onlyEscrowContract {
        NodeInfo storage nodeInfo = nodes[_node];
        require(nodeInfo.lastMinedPeriod == 0);
        nodeInfo.lastMinedPeriod = _period;
    }

    /**
    * @notice Set the minimum reward that the node will take
    **/
    function setMinRewardRate(uint256 _minRewardRate) public {
        NodeInfo storage node = nodes[msg.sender];
        node.minRewardRate = _minRewardRate;
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
        uint256 currentPeriod = getCurrentPeriod();
        policy.startPeriod = currentPeriod.add(uint256(1));
        policy.lastPeriod = currentPeriod.add(_numberOfPeriods);
        policy.rewardRate = msg.value.div(_nodes.length).sub(_firstReward).div(_numberOfPeriods);
        policy.firstReward = _firstReward;
        require(policy.rewardRate > _firstReward &&
            (_firstReward + policy.rewardRate * _numberOfPeriods) * _nodes.length  == msg.value);
        uint256 endPeriod = policy.lastPeriod.add(uint256(1));
        uint256 startReward = policy.rewardRate - _firstReward;

        for (uint256 i = 0; i < _nodes.length; i++) {
            address node = _nodes[i];
            require(node != RESERVED_NODE);
            NodeInfo storage nodeInfo = nodes[node];
            require(nodeInfo.lastMinedPeriod != 0 && policy.rewardRate >= nodeInfo.minRewardRate);
            nodeInfo.rewardDelta[currentPeriod] = nodeInfo.rewardDelta[currentPeriod].add(_firstReward);
            nodeInfo.rewardDelta[policy.startPeriod] = nodeInfo.rewardDelta[policy.startPeriod]
                .add(startReward);
            nodeInfo.rewardDelta[endPeriod] = nodeInfo.rewardDelta[endPeriod].sub(policy.rewardRate);
            policy.arrangements.push(ArrangementInfo(node, escrow.getDowntimeLength(node), 0));
        }

        emit PolicyCreated(_policyId, msg.sender, _nodes);
    }

    /**
    * @notice Update node reward
    * @param _node Node address
    * @param _period Processed period
    **/
    function updateReward(address _node, uint256 _period) external onlyEscrowContract {
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
    * @notice Calculate amount of refund
    * @param _policy Policy
    * @param _arrangement Arrangement
    **/
    function calculateRefundValue(Policy storage _policy, ArrangementInfo storage _arrangement)
        internal view returns (uint256 refundValue, uint256 indexOfDowntimePeriods, uint256 lastRefundedPeriod)
    {
        uint256 maxPeriod = Math.min256(getCurrentPeriod(), _policy.lastPeriod);
        uint256 minPeriod = Math.max256(_policy.startPeriod, _arrangement.lastRefundedPeriod);
        uint256 downtimePeriods = 0;
        uint256 length = escrow.getDowntimeLength(_arrangement.node);
        for (indexOfDowntimePeriods = _arrangement.indexOfDowntimePeriods;
                indexOfDowntimePeriods < length;
                indexOfDowntimePeriods++)
        {
            (uint256 startPeriod, uint256 endPeriod) =
                escrow.getDowntime(_arrangement.node, indexOfDowntimePeriods);
            if (startPeriod > maxPeriod) {
                break;
            } else if (endPeriod < minPeriod) {
                continue;
            }
            downtimePeriods = downtimePeriods.add(
                Math.min256(maxPeriod, endPeriod)
                .sub(Math.max256(minPeriod, startPeriod))
                .add(uint256(1)));
            if (maxPeriod <= endPeriod) {
                break;
            }
        }

        uint256 lastActivePeriod = escrow.getLastActivePeriod(_arrangement.node);
        if (indexOfDowntimePeriods == length && lastActivePeriod < maxPeriod) {
            downtimePeriods = downtimePeriods.add(
                maxPeriod.sub(Math.max256(
                    minPeriod.sub(uint256(1)), lastActivePeriod)));
        }

        // check activity for the first period
        if (_arrangement.lastRefundedPeriod == 0) {
            if (lastActivePeriod < _policy.startPeriod - 1) {
                refundValue = _policy.firstReward;
            } else if (_arrangement.indexOfDowntimePeriods < length) {
                (startPeriod, endPeriod) = escrow.getDowntime(_arrangement.node, _arrangement.indexOfDowntimePeriods);
                if (_policy.startPeriod > startPeriod && _policy.startPeriod - 1 <= endPeriod) {
                    refundValue = _policy.firstReward;
                }
            }
        }
        refundValue = refundValue.add(_policy.rewardRate.mul(downtimePeriods));
        lastRefundedPeriod = maxPeriod.add(uint256(1));
    }

    /**
    * @notice Revoke/refund arrangement/policy by the client
    * @param _policyId Policy id
    * @param _node Node that will be excluded or RESERVED_NODE if full policy should be used
    ( @param _forceRevoke Force revoke arrangement/policy
    **/
    function refundInternal(bytes20 _policyId, address _node, bool _forceRevoke)
        internal returns (uint256 refundValue)
    {
        Policy storage policy = policies[_policyId];
        require(policy.client == msg.sender && !policy.disabled);
        uint256 endPeriod = policy.lastPeriod.add(uint256(1));
        uint256 numberOfActive = policy.arrangements.length;
        for (uint256 i = 0; i < policy.arrangements.length; i++) {
            ArrangementInfo storage arrangement = policy.arrangements[i];
            address node = arrangement.node;
            if (node == RESERVED_NODE || _node != RESERVED_NODE && _node != node) {
                numberOfActive--;
                continue;
            }
            uint256 nodeRefundValue;
            (nodeRefundValue, arrangement.indexOfDowntimePeriods, arrangement.lastRefundedPeriod) =
                calculateRefundValue(policy, arrangement);
            if (_forceRevoke) {
                NodeInfo storage nodeInfo = nodes[node];
                nodeInfo.rewardDelta[arrangement.lastRefundedPeriod] =
                    nodeInfo.rewardDelta[arrangement.lastRefundedPeriod].sub(policy.rewardRate);
                nodeInfo.rewardDelta[endPeriod] = nodeInfo.rewardDelta[endPeriod].add(policy.rewardRate);
                nodeRefundValue = nodeRefundValue.add(
                    endPeriod.sub(arrangement.lastRefundedPeriod).mul(policy.rewardRate));
            }
            if (_forceRevoke || arrangement.lastRefundedPeriod > policy.lastPeriod) {
                arrangement.node = RESERVED_NODE;
                numberOfActive--;
                emit ArrangementRevoked(_policyId, msg.sender, node, nodeRefundValue);
            } else {
                emit RefundForArrangement(_policyId, msg.sender, node, nodeRefundValue);
            }

            refundValue = refundValue.add(nodeRefundValue);
            if (_node != RESERVED_NODE) {
               break;
            }
        }
        if (refundValue > 0) {
            msg.sender.transfer(refundValue);
        }
        if (_node == RESERVED_NODE) {
            if (numberOfActive == 0) {
                policy.disabled = true;
                emit PolicyRevoked(_policyId, msg.sender, refundValue);
            } else {
                emit RefundForPolicy(_policyId, msg.sender, refundValue);
            }
        } else {
            // arrangement not found
            require(i < policy.arrangements.length);
        }
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    * @param _node Node or RESERVED_NODE if all nodes should be used
    **/
    function calculateRefundValueInternal(bytes20 _policyId, address _node)
        internal view returns (uint256 refundValue)
    {
        Policy storage policy = policies[_policyId];
        require(msg.sender == policy.client && !policy.disabled);
        for (uint256 i = 0; i < policy.arrangements.length; i++) {
            ArrangementInfo storage arrangement = policy.arrangements[i];
            if (arrangement.node == RESERVED_NODE || _node != RESERVED_NODE && _node != arrangement.node) {
                continue;
            }
            (uint256 nodeRefundValue,,) = calculateRefundValue(policy, arrangement);
            refundValue = refundValue.add(nodeRefundValue);
            if (_node != RESERVED_NODE) {
               break;
            }
        }
        if (_node != RESERVED_NODE) {
            // arrangement not found
            require(i < policy.arrangements.length);
        }
    }

    /**
    * @notice Revoke policy by client
    * @param _policyId Policy id
    **/
    function revokePolicy(bytes20 _policyId) public {
        refundInternal(_policyId, RESERVED_NODE, true);
    }

    /**
    * @notice Revoke arrangement by client
    * @param _policyId Policy id
    * @param _node Node that will be excluded
    **/
    function revokeArrangement(bytes20 _policyId, address _node)
        public returns (uint256 refundValue)
    {
        require(_node != RESERVED_NODE);
        return refundInternal(_policyId, _node, true);
    }

    /**
    * @notice Refund part of fee by client
    * @param _policyId Policy id
    **/
    function refund(bytes20 _policyId) public {
        refundInternal(_policyId, RESERVED_NODE, false);
    }

    /**
    * @notice Refund part of one node's fee by client
    * @param _policyId Policy id
    * @param _node Node address
    **/
    function refund(bytes20 _policyId, address _node)
        public returns (uint256 refundValue)
    {
        require(_node != RESERVED_NODE);
        return refundInternal(_policyId, _node, false);
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    **/
    function calculateRefundValue(bytes20 _policyId)
        external view returns (uint256 refundValue)
    {
        return calculateRefundValueInternal(_policyId, RESERVED_NODE);
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    * @param _node Node
    **/
    function calculateRefundValue(bytes20 _policyId, address _node)
        external view returns (uint256 refundValue)
    {
        require(_node != RESERVED_NODE);
        return calculateRefundValueInternal(_policyId, _node);
    }

    /**
    * @notice Get number of arrangements in the policy
    * @param _policyId Policy id
    **/
    function getArrangementsLength(bytes20 _policyId)
        public view returns (uint256)
    {
        return policies[_policyId].arrangements.length;
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
    function getArrangementInfo(bytes20 _policyId, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (ArrangementInfo)
        public view returns (address node, uint256 indexOfDowntimePeriods, uint256 lastRefundedPeriod)
    {
        ArrangementInfo storage info = policies[_policyId].arrangements[_index];
        node = info.node;
        indexOfDowntimePeriods = info.indexOfDowntimePeriods;
        lastRefundedPeriod = info.lastRefundedPeriod;
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
    function delegateGetArrangementInfo(address _target, bytes20 _policyId, uint256 _index)
        internal returns (ArrangementInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getArrangementInfo(bytes20,uint256)", 2, bytes32(_policyId), bytes32(_index));
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
        require(uint256(delegateGet(_testTarget, "secondsPerPeriod()")) == secondsPerPeriod);
        Policy storage policy = policies[RESERVED_POLICY_ID];
        Policy memory policyToCheck = delegateGetPolicy(_testTarget, RESERVED_POLICY_ID);
        require(policyToCheck.client == policy.client &&
            policyToCheck.rewardRate == policy.rewardRate &&
            policyToCheck.firstReward == policy.firstReward &&
            policyToCheck.startPeriod == policy.startPeriod &&
            policyToCheck.lastPeriod == policy.lastPeriod &&
            policyToCheck.disabled == policy.disabled);

        require(uint256(delegateGet(_testTarget, "getArrangementsLength(bytes20)",
            RESERVED_POLICY_ID)) == policy.arrangements.length);
        ArrangementInfo storage arrangement = policy.arrangements[0];
        ArrangementInfo memory arrangementToCheck = delegateGetArrangementInfo(
            _testTarget, RESERVED_POLICY_ID, 0);
        require(arrangementToCheck.node == arrangement.node &&
            arrangementToCheck.indexOfDowntimePeriods == arrangement.indexOfDowntimePeriods &&
            arrangementToCheck.lastRefundedPeriod == arrangement.lastRefundedPeriod);

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
        secondsPerPeriod = policyManager.secondsPerPeriod();
        // Create fake Policy and NodeInfo to use them in verifyState(address)
        Policy storage policy = policies[RESERVED_POLICY_ID];
        policy.client = owner;
        policy.startPeriod = 1;
        policy.lastPeriod = 2;
        policy.rewardRate = 3;
        policy.firstReward = 4;
        policy.disabled = true;
        policy.arrangements.push(ArrangementInfo(RESERVED_NODE, 11, 22));
        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        nodeInfo.reward = 100;
        nodeInfo.rewardRate = 33;
        nodeInfo.lastMinedPeriod = 44;
        nodeInfo.rewardDelta[11] = 55;
        nodeInfo.minRewardRate = 777;
    }
}