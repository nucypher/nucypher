pragma solidity ^0.6.1;


import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";
import "zeppelin/utils/Address.sol";
import "contracts/lib/AdditionalMath.sol";
import "contracts/lib/SignatureVerifier.sol";
import "contracts/StakingEscrow.sol";
import "contracts/NuCypherToken.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @notice Contract holds policy data and locks fees
* @dev |v2.2.1|
*/
contract PolicyManager is Upgradeable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;
    using AdditionalMath for uint256;
    using AdditionalMath for int256;
    using AdditionalMath for uint16;
    using Address for address payable;

    event PolicyCreated(
        bytes16 indexed policyId,
        address indexed sponsor,
        address indexed owner,
        uint256 rewardRate,
        uint64 startTimestamp,
        uint64 endTimestamp,
        uint256 numberOfNodes
    );
    event ArrangementRevoked(
        bytes16 indexed policyId,
        address indexed sender,
        address indexed node,
        uint256 value
    );
    event RefundForArrangement(
        bytes16 indexed policyId,
        address indexed sender,
        address indexed node,
        uint256 value
    );
    event PolicyRevoked(bytes16 indexed policyId, address indexed sender, uint256 value);
    event RefundForPolicy(bytes16 indexed policyId, address indexed sender, uint256 value);
    event NodeBrokenState(address indexed node, uint16 period);
    event MinRewardRateSet(address indexed node, uint256 value);
    // TODO #1501
    // Range range
    event MinRewardRateRangeSet(address indexed sender, uint256 min, uint256 defaultValue, uint256 max);
    event Withdrawn(address indexed node, address indexed recipient, uint256 value);

    struct ArrangementInfo {
        address node;
        uint256 indexOfDowntimePeriods;
        uint16 lastRefundedPeriod;
    }

    struct Policy {
        address payable sponsor;
        address owner;

        uint256 rewardRate;
        uint64 startTimestamp;
        uint64 endTimestamp;
        bool disabled;

        uint256 reservedSlot1;
        uint256 reservedSlot2;
        uint256 reservedSlot3;
        uint256 reservedSlot4;
        uint256 reservedSlot5;

        ArrangementInfo[] arrangements;
    }

    struct NodeInfo {
        uint256 reward;
        uint256 rewardRate;
        uint16 lastMinedPeriod;
        mapping (uint16 => int256) rewardDelta;
        uint256 minRewardRate;
    }

    struct Range {
        uint256 min;
        uint256 defaultValue;
        uint256 max;
    }

    bytes16 constant RESERVED_POLICY_ID = bytes16(0);
    address constant RESERVED_NODE = address(0);
    // controlled overflow to get max int256
    int256 public constant DEFAULT_REWARD_DELTA = int256((uint256(0) - 1) >> 1);

    StakingEscrow public escrow;
    uint32 public secondsPerPeriod;
    mapping (bytes16 => Policy) public policies;
    mapping (address => NodeInfo) public nodes;
    Range public minRewardRateRange;

    /**
    * @notice Constructor sets address of the escrow contract
    * @param _escrow Escrow contract
    */
    constructor(StakingEscrow _escrow) public {
        // if the input address is not the StakingEscrow then calling `secondsPerPeriod` will throw error
        secondsPerPeriod = _escrow.secondsPerPeriod();
        require(secondsPerPeriod > 0);
        escrow = _escrow;
    }

    /**
    * @dev Checks that sender is the StakingEscrow contract
    */
    modifier onlyEscrowContract()
    {
        require(msg.sender == address(escrow));
        _;
    }

    /**
    * @return Number of current period
    */
    function getCurrentPeriod() public view returns (uint16) {
        return uint16(block.timestamp / secondsPerPeriod);
    }

    /**
    * @notice Register a node
    * @param _node Node address
    * @param _period Initial period
    */
    function register(address _node, uint16 _period) external onlyEscrowContract {
        NodeInfo storage nodeInfo = nodes[_node];
        require(nodeInfo.lastMinedPeriod == 0 && _period < getCurrentPeriod());
        nodeInfo.lastMinedPeriod = _period;
    }

    /**
    * @notice Set range for the minimum reward rate for all nodes
    */
    // TODO # 1501
    // function setMinRewardRateRange(Range calldata _range) external onlyOwner {
    function setMinRewardRateRange(uint256 _min, uint256 _default, uint256 _max) external onlyOwner {
        require(_min <= _default && _default <= _max);
        minRewardRateRange = Range(_min, _default, _max);
        emit MinRewardRateRangeSet(msg.sender, _min, _default, _max);
    }

    /**
    * @notice Set the minimum reward acceptable by node
    * @dev Input value must be within `minRewardRateRange`
    */
    function setMinRewardRate(uint256 _minRewardRate) external {
        require(_minRewardRate >= minRewardRateRange.min &&
            _minRewardRate <= minRewardRateRange.max,
            "The min reward rate must be within permitted range");
        NodeInfo storage nodeInfo = nodes[msg.sender];
        if (nodeInfo.minRewardRate == _minRewardRate) {
            return;
        }
        nodeInfo.minRewardRate = _minRewardRate;
        emit MinRewardRateSet(msg.sender, _minRewardRate);
    }

    /**
    * @notice Get the minimum reward rate acceptable by node
    */
    function getMinRewardRate(NodeInfo storage _nodeInfo) internal view returns (uint256) {
        // if minRewardRate has not been set or is outside the acceptable range
        if (_nodeInfo.minRewardRate == 0 ||
            _nodeInfo.minRewardRate < minRewardRateRange.min ||
            _nodeInfo.minRewardRate > minRewardRateRange.max) {
            return minRewardRateRange.defaultValue;
        } else {
            return _nodeInfo.minRewardRate;
        }
    }

    /**
    * @notice Get the minimum reward rate acceptable by node
    */
    function getMinRewardRate(address _node) public view returns (uint256) {
        NodeInfo storage nodeInfo = nodes[_node];
        return getMinRewardRate(nodeInfo);
    }

    /**
    * @notice Create policy
    * @dev Generate policy id before creation
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _endTimestamp End timestamp of the policy in seconds
    * @param _nodes Nodes that will handle policy
    */
    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _endTimestamp,
        address[] calldata _nodes
    )
        external payable
    {
        Policy storage policy = policies[_policyId];
        require(
            _policyId != RESERVED_POLICY_ID &&
            policy.rewardRate == 0 &&
            _endTimestamp > block.timestamp &&
            msg.value > 0
        );
        uint16 currentPeriod = getCurrentPeriod();
        uint16 endPeriod = uint16(_endTimestamp / secondsPerPeriod) + 1;
        uint256 numberOfPeriods = endPeriod - currentPeriod;

        policy.sponsor = msg.sender;
        policy.startTimestamp = uint64(block.timestamp);
        policy.endTimestamp = _endTimestamp;
        policy.rewardRate = msg.value.div(_nodes.length) / numberOfPeriods;
        require(policy.rewardRate > 0 && policy.rewardRate * numberOfPeriods * _nodes.length  == msg.value);
        if (_policyOwner != msg.sender && _policyOwner != address(0)) {
            policy.owner = _policyOwner;
        }

        for (uint256 i = 0; i < _nodes.length; i++) {
            address node = _nodes[i];
            require(node != RESERVED_NODE);
            NodeInfo storage nodeInfo = nodes[node];
            require(nodeInfo.lastMinedPeriod != 0 &&
                nodeInfo.lastMinedPeriod < currentPeriod &&
                policy.rewardRate >= getMinRewardRate(nodeInfo));
            // Check default value for rewardDelta
            if (nodeInfo.rewardDelta[currentPeriod] == DEFAULT_REWARD_DELTA) {
                nodeInfo.rewardDelta[currentPeriod] = int256(policy.rewardRate);
            } else {
                // Overflow protection removed, because ETH total supply less than uint255/int256
                nodeInfo.rewardDelta[currentPeriod] += int256(policy.rewardRate);
            }
            if (nodeInfo.rewardDelta[endPeriod] == DEFAULT_REWARD_DELTA) {
                nodeInfo.rewardDelta[endPeriod] = -int256(policy.rewardRate);
            } else {
                nodeInfo.rewardDelta[endPeriod] -= int256(policy.rewardRate);
            }
            // Reset to default value if needed
            if (nodeInfo.rewardDelta[currentPeriod] == 0) {
                nodeInfo.rewardDelta[currentPeriod] = DEFAULT_REWARD_DELTA;
            }
            if (nodeInfo.rewardDelta[endPeriod] == 0) {
                nodeInfo.rewardDelta[endPeriod] = DEFAULT_REWARD_DELTA;
            }
            policy.arrangements.push(ArrangementInfo(node, 0, 0));
        }

        emit PolicyCreated(
            _policyId,
            msg.sender,
            _policyOwner == address(0) ? msg.sender : _policyOwner,
            policy.rewardRate,
            policy.startTimestamp,
            policy.endTimestamp,
            _nodes.length
        );
    }

    /**
    * @notice Get policy owner
    */
    function getPolicyOwner(bytes16 _policyId) public view returns (address) {
        Policy storage policy = policies[_policyId];
        return policy.owner == address(0) ? policy.sponsor : policy.owner;
    }

    /**
    * @notice Set default `rewardDelta` value for specified period
    * @dev This method increases gas cost for node in trade of decreasing cost for policy sponsor
    * @param _node Node address
    * @param _period Period to set
    */
    function setDefaultRewardDelta(address _node, uint16 _period) external onlyEscrowContract {
        NodeInfo storage node = nodes[_node];
        if (node.rewardDelta[_period] == 0) {
            node.rewardDelta[_period] = DEFAULT_REWARD_DELTA;
        }
    }

    /**
    * @notice Update node reward
    * @param _node Node address
    * @param _period Processed period
    */
    function updateReward(address _node, uint16 _period) external onlyEscrowContract {
        NodeInfo storage node = nodes[_node];
        if (node.lastMinedPeriod == 0 || _period <= node.lastMinedPeriod) {
            return;
        }
        for (uint16 i = node.lastMinedPeriod + 1; i <= _period; i++) {
            int256 delta = node.rewardDelta[i];
            if (delta == DEFAULT_REWARD_DELTA) {
                // gas refund
                node.rewardDelta[i] = 0;
                continue;
            }

            // broken state
            if (delta < 0 && uint256(-delta) > node.rewardRate) {
                node.rewardDelta[i] += int256(node.rewardRate);
                node.rewardRate = 0;
                emit NodeBrokenState(_node, _period);
            // good state
            } else {
                node.rewardRate = node.rewardRate.addSigned(delta);
                // gas refund
                node.rewardDelta[i] = 0;
            }
        }
        node.lastMinedPeriod = _period;
        node.reward += node.rewardRate;
    }

    /**
    * @notice Withdraw reward by node
    */
    function withdraw() external returns (uint256) {
        return withdraw(msg.sender);
    }

    /**
    * @notice Withdraw reward by node
    * @param _recipient Recipient of the reward
    */
    function withdraw(address payable _recipient) public returns (uint256) {
        NodeInfo storage node = nodes[msg.sender];
        uint256 reward = node.reward;
        require(reward != 0);
        node.reward = 0;
        _recipient.sendValue(reward);
        emit Withdrawn(msg.sender, _recipient, reward);
        return reward;
    }

    /**
    * @notice Calculate amount of refund
    * @param _policy Policy
    * @param _arrangement Arrangement
    */
    function calculateRefundValue(Policy storage _policy, ArrangementInfo storage _arrangement)
        internal view returns (uint256 refundValue, uint256 indexOfDowntimePeriods, uint16 lastRefundedPeriod)
    {
        uint16 policyStartPeriod = uint16(_policy.startTimestamp / secondsPerPeriod);
        uint16 maxPeriod = AdditionalMath.min16(getCurrentPeriod(), uint16(_policy.endTimestamp / secondsPerPeriod));
        uint16 minPeriod = AdditionalMath.max16(policyStartPeriod, _arrangement.lastRefundedPeriod);
        uint16 downtimePeriods = 0;
        uint256 length = escrow.getPastDowntimeLength(_arrangement.node);
        uint256 initialIndexOfDowntimePeriods;
        if (_arrangement.lastRefundedPeriod == 0) {
            initialIndexOfDowntimePeriods = escrow.findIndexOfPastDowntime(_arrangement.node, policyStartPeriod);
        } else {
            initialIndexOfDowntimePeriods = _arrangement.indexOfDowntimePeriods;
        }

        for (indexOfDowntimePeriods = initialIndexOfDowntimePeriods;
             indexOfDowntimePeriods < length;
             indexOfDowntimePeriods++)
        {
            (uint16 startPeriod, uint16 endPeriod) =
                escrow.getPastDowntime(_arrangement.node, indexOfDowntimePeriods);
            if (startPeriod > maxPeriod) {
                break;
            } else if (endPeriod < minPeriod) {
                continue;
            }
            downtimePeriods += AdditionalMath.min16(maxPeriod, endPeriod)
                .sub16(AdditionalMath.max16(minPeriod, startPeriod)) + 1;
            if (maxPeriod <= endPeriod) {
                break;
            }
        }

        uint16 lastActivePeriod = escrow.getLastActivePeriod(_arrangement.node);
        if (indexOfDowntimePeriods == length && lastActivePeriod < maxPeriod) {
            // Overflow protection removed:
            // lastActivePeriod < maxPeriod and minPeriod <= maxPeriod + 1
            downtimePeriods += maxPeriod - AdditionalMath.max16(minPeriod - 1, lastActivePeriod);
        }

        refundValue = _policy.rewardRate * downtimePeriods;
        lastRefundedPeriod = maxPeriod + 1;
    }

    /**
    * @notice Revoke/refund arrangement/policy by the sponsor
    * @param _policyId Policy id
    * @param _node Node that will be excluded or RESERVED_NODE if full policy should be used
    ( @param _forceRevoke Force revoke arrangement/policy
    */
    function refundInternal(bytes16 _policyId, address _node, bool _forceRevoke)
        internal returns (uint256 refundValue)
    {
        refundValue = 0;
        Policy storage policy = policies[_policyId];
        require(!policy.disabled);
        uint16 endPeriod = uint16(policy.endTimestamp / secondsPerPeriod) + 1;
        uint256 numberOfActive = policy.arrangements.length;
        uint256 i = 0;
        for (; i < policy.arrangements.length; i++) {
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

                // Check default value for rewardDelta
                uint16 lastRefundedPeriod = arrangement.lastRefundedPeriod;
                if (nodeInfo.rewardDelta[lastRefundedPeriod] == DEFAULT_REWARD_DELTA) {
                    nodeInfo.rewardDelta[lastRefundedPeriod] = -int256(policy.rewardRate);
                } else {
                    nodeInfo.rewardDelta[lastRefundedPeriod] -= int256(policy.rewardRate);
                }
                if (nodeInfo.rewardDelta[endPeriod] == DEFAULT_REWARD_DELTA) {
                    nodeInfo.rewardDelta[endPeriod] = -int256(policy.rewardRate);
                } else {
                    nodeInfo.rewardDelta[endPeriod] += int256(policy.rewardRate);
                }

                // Reset to default value if needed
                if (nodeInfo.rewardDelta[lastRefundedPeriod] == 0) {
                    nodeInfo.rewardDelta[lastRefundedPeriod] = DEFAULT_REWARD_DELTA;
                }
                if (nodeInfo.rewardDelta[endPeriod] == 0) {
                    nodeInfo.rewardDelta[endPeriod] = DEFAULT_REWARD_DELTA;
                }
                nodeRefundValue += uint256(endPeriod - lastRefundedPeriod) * policy.rewardRate;
            }
            if (_forceRevoke || arrangement.lastRefundedPeriod >= endPeriod) {
                arrangement.node = RESERVED_NODE;
                arrangement.indexOfDowntimePeriods = 0;
                arrangement.lastRefundedPeriod = 0;
                numberOfActive--;
                emit ArrangementRevoked(_policyId, msg.sender, node, nodeRefundValue);
            } else {
                emit RefundForArrangement(_policyId, msg.sender, node, nodeRefundValue);
            }

            refundValue += nodeRefundValue;
            if (_node != RESERVED_NODE) {
               break;
            }
        }
        address payable policySponsor = policy.sponsor;
        if (_node == RESERVED_NODE) {
            if (numberOfActive == 0) {
                policy.disabled = true;
                // gas refund
                // deletion more slots will increase gas usage instead of decreasing (in current code)
                // because gas refund can be no more than half of all gas
                policy.sponsor = address(0);
                emit PolicyRevoked(_policyId, msg.sender, refundValue);
            } else {
                emit RefundForPolicy(_policyId, msg.sender, refundValue);
            }
        } else {
            // arrangement not found
            require(i < policy.arrangements.length);
        }
        if (refundValue > 0) {
            policySponsor.sendValue(refundValue);
        }
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    * @param _node Node or RESERVED_NODE if all nodes should be used
    */
    function calculateRefundValueInternal(bytes16 _policyId, address _node)
        internal view returns (uint256 refundValue)
    {
        refundValue = 0;
        Policy storage policy = policies[_policyId];
        require((policy.owner == msg.sender || policy.sponsor == msg.sender) && !policy.disabled);
        uint256 i = 0;
        for (; i < policy.arrangements.length; i++) {
            ArrangementInfo storage arrangement = policy.arrangements[i];
            if (arrangement.node == RESERVED_NODE || _node != RESERVED_NODE && _node != arrangement.node) {
                continue;
            }
            (uint256 nodeRefundValue,,) = calculateRefundValue(policy, arrangement);
            refundValue += nodeRefundValue;
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
    * @notice Revoke policy by the sponsor
    * @param _policyId Policy id
    */
    function revokePolicy(bytes16 _policyId) external returns (uint256 refundValue) {
        require(getPolicyOwner(_policyId) == msg.sender);
        return refundInternal(_policyId, RESERVED_NODE, true);
    }

    /**
    * @notice Revoke arrangement by the sponsor
    * @param _policyId Policy id
    * @param _node Node that will be excluded
    */
    function revokeArrangement(bytes16 _policyId, address _node)
        external returns (uint256 refundValue)
    {
        require(_node != RESERVED_NODE);
        require(getPolicyOwner(_policyId) == msg.sender);
        return refundInternal(_policyId, _node, true);
    }

    /**
    * @notice Get unsigned hash for revocation
    * @param _policyId Policy id
    * @param _node Node that will be excluded
    * @return Revocation hash, EIP191 version 0x45 ('E')
    */
    function getRevocationHash(bytes16 _policyId, address _node) public view returns (bytes32) {
        return SignatureVerifier.hashEIP191(abi.encodePacked(_policyId, _node), byte(0x45));
    }

    /**
    * @notice Check correctness of signature
    * @param _policyId Policy id
    * @param _node Node that will be excluded, zero address if whole policy will be revoked
    * @param _signature Signature of owner
    */
    function checkOwnerSignature(bytes16 _policyId, address _node, bytes memory _signature) internal view {
        bytes32 hash = getRevocationHash(_policyId, _node);
        address recovered = SignatureVerifier.recover(hash, _signature);
        require(getPolicyOwner(_policyId) == recovered);
    }

    /**
    * @notice Revoke policy or arrangement using owner's signature
    * @param _policyId Policy id
    * @param _node Node that will be excluded, zero address if whole policy will be revoked
    * @param _signature Signature of owner, EIP191 version 0x45 ('E')
    */
    function revoke(bytes16 _policyId, address _node, bytes calldata _signature)
        external returns (uint256 refundValue)
    {
        checkOwnerSignature(_policyId, _node, _signature);
        return refundInternal(_policyId, _node, true);
    }

    /**
    * @notice Refund part of fee by the sponsor
    * @param _policyId Policy id
    */
    function refund(bytes16 _policyId) external {
        Policy storage policy = policies[_policyId];
        require(policy.owner == msg.sender || policy.sponsor == msg.sender);
        refundInternal(_policyId, RESERVED_NODE, false);
    }

    /**
    * @notice Refund part of one node's fee by the sponsor
    * @param _policyId Policy id
    * @param _node Node address
    */
    function refund(bytes16 _policyId, address _node)
        external returns (uint256 refundValue)
    {
        require(_node != RESERVED_NODE);
        Policy storage policy = policies[_policyId];
        require(policy.owner == msg.sender || policy.sponsor == msg.sender);
        return refundInternal(_policyId, _node, false);
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    */
    function calculateRefundValue(bytes16 _policyId)
        external view returns (uint256 refundValue)
    {
        return calculateRefundValueInternal(_policyId, RESERVED_NODE);
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    * @param _node Node
    */
    function calculateRefundValue(bytes16 _policyId, address _node)
        external view returns (uint256 refundValue)
    {
        require(_node != RESERVED_NODE);
        return calculateRefundValueInternal(_policyId, _node);
    }

    /**
    * @notice Get number of arrangements in the policy
    * @param _policyId Policy id
    */
    function getArrangementsLength(bytes16 _policyId) external view returns (uint256) {
        return policies[_policyId].arrangements.length;
    }

    /**
    * @notice Get information about node reward
    * @param _node Address of node
    * @param _period Period to get reward delta
    */
    function getNodeRewardDelta(address _node, uint16 _period)
        // TODO "virtual" only for tests, probably will be removed after #1512
        external view virtual returns (int256)
    {
        return nodes[_node].rewardDelta[_period];
    }

    /**
    * @notice Return the information about arrangement
    */
    function getArrangementInfo(bytes16 _policyId, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released (#1501)
//        public view returns (ArrangementInfo)
        external view returns (address node, uint256 indexOfDowntimePeriods, uint16 lastRefundedPeriod)
    {
        ArrangementInfo storage info = policies[_policyId].arrangements[_index];
        node = info.node;
        indexOfDowntimePeriods = info.indexOfDowntimePeriods;
        lastRefundedPeriod = info.lastRefundedPeriod;
    }


    /**
    * @dev Get Policy structure by delegatecall
    */
    function delegateGetPolicy(address _target, bytes16 _policyId)
        internal returns (Policy memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, this.policies.selector, 1, bytes32(_policyId), 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get ArrangementInfo structure by delegatecall
    */
    function delegateGetArrangementInfo(address _target, bytes16 _policyId, uint256 _index)
        internal returns (ArrangementInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, this.getArrangementInfo.selector, 2, bytes32(_policyId), bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get NodeInfo structure by delegatecall
    */
    function delegateGetNodeInfo(address _target, address _node)
        internal returns (NodeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, this.nodes.selector, 1, bytes32(uint256(_node)), 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get minRewardRateRange structure by delegatecall
    */
    function delegateGetMinRewardRateRange(address _target) internal returns (Range memory result) {
        bytes32 memoryAddress = delegateGetData(_target, this.minRewardRateRange.selector, 0, 0, 0);
        assembly {
            result := memoryAddress
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(address(delegateGet(_testTarget, this.escrow.selector)) == address(escrow));
        require(uint32(delegateGet(_testTarget, this.secondsPerPeriod.selector)) == secondsPerPeriod);
        Range memory rangeToCheck = delegateGetMinRewardRateRange(_testTarget);
        require(minRewardRateRange.min == rangeToCheck.min &&
            minRewardRateRange.defaultValue == rangeToCheck.defaultValue &&
            minRewardRateRange.max == rangeToCheck.max);
        Policy storage policy = policies[RESERVED_POLICY_ID];
        Policy memory policyToCheck = delegateGetPolicy(_testTarget, RESERVED_POLICY_ID);
        require(policyToCheck.sponsor == policy.sponsor &&
            policyToCheck.owner == policy.owner &&
            policyToCheck.rewardRate == policy.rewardRate &&
            policyToCheck.startTimestamp == policy.startTimestamp &&
            policyToCheck.endTimestamp == policy.endTimestamp &&
            policyToCheck.disabled == policy.disabled);

        require(delegateGet(_testTarget, this.getArrangementsLength.selector, RESERVED_POLICY_ID) ==
            policy.arrangements.length);
        if (policy.arrangements.length > 0) {
            ArrangementInfo storage arrangement = policy.arrangements[0];
            ArrangementInfo memory arrangementToCheck = delegateGetArrangementInfo(
                _testTarget, RESERVED_POLICY_ID, 0);
            require(arrangementToCheck.node == arrangement.node &&
                arrangementToCheck.indexOfDowntimePeriods == arrangement.indexOfDowntimePeriods &&
                arrangementToCheck.lastRefundedPeriod == arrangement.lastRefundedPeriod);
        }

        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        NodeInfo memory nodeInfoToCheck = delegateGetNodeInfo(_testTarget, RESERVED_NODE);
        require(nodeInfoToCheck.reward == nodeInfo.reward &&
            nodeInfoToCheck.rewardRate == nodeInfo.rewardRate &&
            nodeInfoToCheck.lastMinedPeriod == nodeInfo.lastMinedPeriod &&
            nodeInfoToCheck.minRewardRate == nodeInfo.minRewardRate);

        require(int256(delegateGet(_testTarget, this.getNodeRewardDelta.selector,
            bytes32(bytes20(RESERVED_NODE)), bytes32(uint256(11)))) == nodeInfo.rewardDelta[11]);
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public override virtual {
        super.finishUpgrade(_target);
        PolicyManager policyManager = PolicyManager(_target);
        escrow = policyManager.escrow();
        secondsPerPeriod = policyManager.secondsPerPeriod();
        // Create fake Policy and NodeInfo to use them in verifyState(address)
        Policy storage policy = policies[RESERVED_POLICY_ID];
        policy.sponsor = msg.sender;
        policy.owner = address(this);
        policy.startTimestamp = 1;
        policy.endTimestamp = 2;
        policy.rewardRate = 3;
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
