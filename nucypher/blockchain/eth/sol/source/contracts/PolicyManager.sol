// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


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
* @title PolicyManager
* @notice Contract holds policy data and locks accrued policy fees
* @dev |v6.3.2|
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
        uint256 feeRate,
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
    event MinFeeRateSet(address indexed node, uint256 value);
    // TODO #1501
    // Range range
    event FeeRateRangeSet(address indexed sender, uint256 min, uint256 defaultValue, uint256 max);
    event Withdrawn(address indexed node, address indexed recipient, uint256 value);

    struct ArrangementInfo {
        address node;
        uint256 indexOfDowntimePeriods;
        uint16 lastRefundedPeriod;
    }

    struct Policy {
        bool disabled;
        address payable sponsor;
        address owner;

        uint128 feeRate;
        uint64 startTimestamp;
        uint64 endTimestamp;

        uint256 reservedSlot1;
        uint256 reservedSlot2;
        uint256 reservedSlot3;
        uint256 reservedSlot4;
        uint256 reservedSlot5;

        ArrangementInfo[] arrangements;
    }

    struct NodeInfo {
        uint128 fee;
        uint16 previousFeePeriod;
        uint256 feeRate;
        uint256 minFeeRate;
        mapping (uint16 => int256) stub; // former slot for feeDelta
        mapping (uint16 => int256) feeDelta;
    }

    // TODO used only for `delegateGetNodeInfo`, probably will be removed after #1512
    struct MemoryNodeInfo {
        uint128 fee;
        uint16 previousFeePeriod;
        uint256 feeRate;
        uint256 minFeeRate;
    }

    struct Range {
        uint128 min;
        uint128 defaultValue;
        uint128 max;
    }

    bytes16 internal constant RESERVED_POLICY_ID = bytes16(0);
    address internal constant RESERVED_NODE = address(0);
    uint256 internal constant MAX_BALANCE = uint256(uint128(0) - 1);
    // controlled overflow to get max int256
    int256 public constant DEFAULT_FEE_DELTA = int256((uint256(0) - 1) >> 1);

    StakingEscrow public immutable escrow;
    uint32 public immutable genesisSecondsPerPeriod;
    uint32 public immutable secondsPerPeriod;

    mapping (bytes16 => Policy) public policies;
    mapping (address => NodeInfo) public nodes;
    Range public feeRateRange;
    uint64 public resetTimestamp;

    /**
    * @notice Constructor sets address of the escrow contract
    * @dev Put same address in both inputs variables except when migration is happening
    * @param _escrowDispatcher Address of escrow dispatcher
    * @param _escrowImplementation Address of escrow implementation
    */
    constructor(StakingEscrow _escrowDispatcher, StakingEscrow _escrowImplementation) {
        escrow = _escrowDispatcher;
        // if the input address is not the StakingEscrow then calling `secondsPerPeriod` will throw error
        uint32 localSecondsPerPeriod = _escrowImplementation.secondsPerPeriod();
        require(localSecondsPerPeriod > 0);
        secondsPerPeriod = localSecondsPerPeriod;
        uint32 localgenesisSecondsPerPeriod = _escrowImplementation.genesisSecondsPerPeriod();
        require(localgenesisSecondsPerPeriod > 0);
        genesisSecondsPerPeriod = localgenesisSecondsPerPeriod;
        // handle case when we deployed new StakingEscrow but not yet upgraded
        if (_escrowDispatcher != _escrowImplementation) {
            require(_escrowDispatcher.secondsPerPeriod() == localSecondsPerPeriod ||
                _escrowDispatcher.secondsPerPeriod() == localgenesisSecondsPerPeriod);
        }
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
    * @return Recalculate period value using new basis
    */
    function recalculatePeriod(uint16 _period) internal view returns (uint16) {
        return uint16(uint256(_period) * genesisSecondsPerPeriod / secondsPerPeriod);
    }

    /**
    * @notice Register a node
    * @param _node Node address
    * @param _period Initial period
    */
    function register(address _node, uint16 _period) external onlyEscrowContract {
        NodeInfo storage nodeInfo = nodes[_node];
        require(nodeInfo.previousFeePeriod == 0 && _period < getCurrentPeriod());
        nodeInfo.previousFeePeriod = _period;
    }

    /**
    * @notice Migrate from the old period length to the new one
    * @param _node Node address
    */
    function migrate(address _node) external onlyEscrowContract {
        NodeInfo storage nodeInfo = nodes[_node];
        uint16 currentPeriod = getCurrentPeriod();
        // with previous period length any previousFeePeriod will be greater than current period
        // this is a sign of not migrated node
        require(nodeInfo.previousFeePeriod >= currentPeriod);
        nodeInfo.previousFeePeriod = currentPeriod - 1;
        nodeInfo.feeRate = 0;
    }

    /**
    * @notice Set minimum, default & maximum fee rate for all stakers and all policies ('global fee range')
    */
    // TODO # 1501
    // function setFeeRateRange(Range calldata _range) external onlyOwner {
    function setFeeRateRange(uint128 _min, uint128 _default, uint128 _max) external onlyOwner {
        require(_min <= _default && _default <= _max);
        feeRateRange = Range(_min, _default, _max);
        emit FeeRateRangeSet(msg.sender, _min, _default, _max);
    }

    /**
    * @notice Set the minimum acceptable fee rate (set by staker for their associated worker)
    * @dev Input value must fall within `feeRateRange` (global fee range)
    */
    function setMinFeeRate(uint256 _minFeeRate) external {
        require(_minFeeRate >= feeRateRange.min &&
            _minFeeRate <= feeRateRange.max,
            "The staker's min fee rate must fall within the global fee range");
        NodeInfo storage nodeInfo = nodes[msg.sender];
        if (nodeInfo.minFeeRate == _minFeeRate) {
            return;
        }
        nodeInfo.minFeeRate = _minFeeRate;
        emit MinFeeRateSet(msg.sender, _minFeeRate);
    }

    /**
    * @notice Get the minimum acceptable fee rate (set by staker for their associated worker)
    */
    function getMinFeeRate(NodeInfo storage _nodeInfo) internal view returns (uint256) {
        // if minFeeRate has not been set or chosen value falls outside the global fee range
        // a default value is returned instead
        if (_nodeInfo.minFeeRate == 0 ||
            _nodeInfo.minFeeRate < feeRateRange.min ||
            _nodeInfo.minFeeRate > feeRateRange.max) {
            return feeRateRange.defaultValue;
        } else {
            return _nodeInfo.minFeeRate;
        }
    }

    /**
    * @notice Get the minimum acceptable fee rate (set by staker for their associated worker)
    */
    function getMinFeeRate(address _node) public view returns (uint256) {
        NodeInfo storage nodeInfo = nodes[_node];
        return getMinFeeRate(nodeInfo);
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
        require(
            _endTimestamp > block.timestamp &&
            msg.value > 0
        );

        require(address(this).balance <= MAX_BALANCE);
        uint16 currentPeriod = getCurrentPeriod();
        uint16 endPeriod = uint16(_endTimestamp / secondsPerPeriod) + 1;
        uint256 numberOfPeriods = endPeriod - currentPeriod;

        uint128 feeRate = uint128(msg.value.div(_nodes.length) / numberOfPeriods);
        require(feeRate > 0 && feeRate * numberOfPeriods * _nodes.length  == msg.value);

        Policy storage policy = createPolicy(_policyId, _policyOwner, _endTimestamp, feeRate, _nodes.length);

        for (uint256 i = 0; i < _nodes.length; i++) {
            address node = _nodes[i];
            addFeeToNode(currentPeriod, endPeriod, node, feeRate, int256(feeRate));
            policy.arrangements.push(ArrangementInfo(node, 0, 0));
        }
    }

    /**
    * @notice Create multiple policies with the same owner, nodes and length
    * @dev Generate policy ids before creation
    * @param _policyIds Policy ids
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _endTimestamp End timestamp of all policies in seconds
    * @param _nodes Nodes that will handle all policies
    */
    function createPolicies(
        bytes16[] calldata _policyIds,
        address _policyOwner,
        uint64 _endTimestamp,
        address[] calldata _nodes
    )
        external payable
    {
        require(
            _endTimestamp > block.timestamp &&
            msg.value > 0 &&
            _policyIds.length > 1
        );

        require(address(this).balance <= MAX_BALANCE);
        uint16 currentPeriod = getCurrentPeriod();
        uint16 endPeriod = uint16(_endTimestamp / secondsPerPeriod) + 1;
        uint256 numberOfPeriods = endPeriod - currentPeriod;

        uint128 feeRate = uint128(msg.value.div(_nodes.length) / numberOfPeriods / _policyIds.length);
        require(feeRate > 0 && feeRate * numberOfPeriods * _nodes.length * _policyIds.length == msg.value);

        for (uint256 i = 0; i < _policyIds.length; i++) {
            Policy storage policy = createPolicy(_policyIds[i], _policyOwner, _endTimestamp, feeRate, _nodes.length);

            for (uint256 j = 0; j < _nodes.length; j++) {
                policy.arrangements.push(ArrangementInfo(_nodes[j], 0, 0));
            }
        }

        int256 fee = int256(_policyIds.length * feeRate);

        for (uint256 i = 0; i < _nodes.length; i++) {
            address node = _nodes[i];
            addFeeToNode(currentPeriod, endPeriod, node, feeRate, fee);
        }
    }

    /**
    * @notice Create policy
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _endTimestamp End timestamp of the policy in seconds
    * @param _feeRate Fee rate for policy
    * @param _nodesLength Number of nodes that will handle policy
    */
    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _endTimestamp,
        uint128 _feeRate,
        uint256 _nodesLength
    )
        internal returns (Policy storage policy)
    {
        policy = policies[_policyId];
        require(
            _policyId != RESERVED_POLICY_ID &&
            policy.feeRate == 0 &&
            !policy.disabled
        );

        policy.sponsor = msg.sender;
        policy.startTimestamp = uint64(block.timestamp);
        policy.endTimestamp = _endTimestamp;
        policy.feeRate = _feeRate;

        if (_policyOwner != msg.sender && _policyOwner != address(0)) {
            policy.owner = _policyOwner;
        }

        emit PolicyCreated(
            _policyId,
            msg.sender,
            _policyOwner == address(0) ? msg.sender : _policyOwner,
            _feeRate,
            policy.startTimestamp,
            policy.endTimestamp,
            _nodesLength
        );
    }

    /**
    * @notice Increase fee rate for specified node
    * @param _currentPeriod Current period
    * @param _endPeriod End period of policy
    * @param _node Node that will handle policy
    * @param _feeRate Fee rate for one policy
    * @param _overallFeeRate Fee rate for all policies
    */
    function addFeeToNode(
        uint16 _currentPeriod,
        uint16 _endPeriod,
        address _node,
        uint128 _feeRate,
        int256 _overallFeeRate
    )
        internal
    {
        require(_node != RESERVED_NODE);
        NodeInfo storage nodeInfo = nodes[_node];
        require(nodeInfo.previousFeePeriod != 0 &&
            nodeInfo.previousFeePeriod < _currentPeriod &&
            _feeRate >= getMinFeeRate(nodeInfo));
        // Check default value for feeDelta
        if (nodeInfo.feeDelta[_currentPeriod] == DEFAULT_FEE_DELTA) {
            nodeInfo.feeDelta[_currentPeriod] = _overallFeeRate;
        } else {
            // Overflow protection removed, because ETH total supply less than uint255/int256
            nodeInfo.feeDelta[_currentPeriod] += _overallFeeRate;
        }
        if (nodeInfo.feeDelta[_endPeriod] == DEFAULT_FEE_DELTA) {
            nodeInfo.feeDelta[_endPeriod] = -_overallFeeRate;
        } else {
            nodeInfo.feeDelta[_endPeriod] -= _overallFeeRate;
        }
        // Reset to default value if needed
        if (nodeInfo.feeDelta[_currentPeriod] == 0) {
            nodeInfo.feeDelta[_currentPeriod] = DEFAULT_FEE_DELTA;
        }
        if (nodeInfo.feeDelta[_endPeriod] == 0) {
            nodeInfo.feeDelta[_endPeriod] = DEFAULT_FEE_DELTA;
        }
    }

    /**
    * @notice Get policy owner
    */
    function getPolicyOwner(bytes16 _policyId) public view returns (address) {
        Policy storage policy = policies[_policyId];
        return policy.owner == address(0) ? policy.sponsor : policy.owner;
    }

    /**
    * @notice Call from StakingEscrow to update node info once per period.
    * Set default `feeDelta` value for specified period and update node fee
    * @param _node Node address
    * @param _processedPeriod1 Processed period
    * @param _processedPeriod2 Processed period
    * @param _periodToSetDefault Period to set
    */
    function ping(
        address _node,
        uint16 _processedPeriod1,
        uint16 _processedPeriod2,
        uint16 _periodToSetDefault
    )
        external onlyEscrowContract
    {
        NodeInfo storage node = nodes[_node];
        // protection from calling not migrated node, see migrate()
        require(node.previousFeePeriod < getCurrentPeriod());
        if (_processedPeriod1 != 0) {
            updateFee(node, _processedPeriod1);
        }
        if (_processedPeriod2 != 0) {
            updateFee(node, _processedPeriod2);
        }
        // This code increases gas cost for node in trade of decreasing cost for policy sponsor
        if (_periodToSetDefault != 0 && node.feeDelta[_periodToSetDefault] == 0) {
            node.feeDelta[_periodToSetDefault] = DEFAULT_FEE_DELTA;
        }
    }

    /**
    * @notice Update node fee
    * @param _info Node info structure
    * @param _period Processed period
    */
    function updateFee(NodeInfo storage _info, uint16 _period) internal {
        if (_info.previousFeePeriod == 0 || _period <= _info.previousFeePeriod) {
            return;
        }
        for (uint16 i = _info.previousFeePeriod + 1; i <= _period; i++) {
            int256 delta = _info.feeDelta[i];
            if (delta == DEFAULT_FEE_DELTA) {
                // gas refund
                _info.feeDelta[i] = 0;
                continue;
            }

            _info.feeRate = _info.feeRate.addSigned(delta);
            // gas refund
            _info.feeDelta[i] = 0;
        }
        _info.previousFeePeriod = _period;
        _info.fee += uint128(_info.feeRate);
    }

    /**
    * @notice Withdraw fee by node
    */
    function withdraw() external returns (uint256) {
        return withdraw(msg.sender);
    }

    /**
    * @notice Withdraw fee by node
    * @param _recipient Recipient of the fee
    */
    function withdraw(address payable _recipient) public returns (uint256) {
        NodeInfo storage node = nodes[msg.sender];
        uint256 fee = node.fee;
        require(fee != 0);
        node.fee = 0;
        _recipient.sendValue(fee);
        emit Withdrawn(msg.sender, _recipient, fee);
        return fee;
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

        uint16 lastCommittedPeriod = escrow.getLastCommittedPeriod(_arrangement.node);
        if (indexOfDowntimePeriods == length && lastCommittedPeriod < maxPeriod) {
            // Overflow protection removed:
            // lastCommittedPeriod < maxPeriod and minPeriod <= maxPeriod + 1
            downtimePeriods += maxPeriod - AdditionalMath.max16(minPeriod - 1, lastCommittedPeriod);
        }

        refundValue = _policy.feeRate * downtimePeriods;
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
        require(!policy.disabled && policy.startTimestamp >= resetTimestamp);
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

                // Check default value for feeDelta
                uint16 lastRefundedPeriod = arrangement.lastRefundedPeriod;
                if (nodeInfo.feeDelta[lastRefundedPeriod] == DEFAULT_FEE_DELTA) {
                    nodeInfo.feeDelta[lastRefundedPeriod] = -int256(policy.feeRate);
                } else {
                    nodeInfo.feeDelta[lastRefundedPeriod] -= int256(policy.feeRate);
                }
                if (nodeInfo.feeDelta[endPeriod] == DEFAULT_FEE_DELTA) {
                    nodeInfo.feeDelta[endPeriod] = int256(policy.feeRate);
                } else {
                    nodeInfo.feeDelta[endPeriod] += int256(policy.feeRate);
                }

                // Reset to default value if needed
                if (nodeInfo.feeDelta[lastRefundedPeriod] == 0) {
                    nodeInfo.feeDelta[lastRefundedPeriod] = DEFAULT_FEE_DELTA;
                }
                if (nodeInfo.feeDelta[endPeriod] == 0) {
                    nodeInfo.feeDelta[endPeriod] = DEFAULT_FEE_DELTA;
                }
                nodeRefundValue += uint256(endPeriod - lastRefundedPeriod) * policy.feeRate;
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
                policy.sponsor = address(0);
                policy.owner = address(0);
                policy.feeRate = 0;
                policy.startTimestamp = 0;
                policy.endTimestamp = 0;
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
    * @notice Get information about staker's fee rate
    * @param _node Address of staker
    * @param _period Period to get fee delta
    */
    function getNodeFeeDelta(address _node, uint16 _period)
        // TODO "virtual" only for tests, probably will be removed after #1512
        public view virtual returns (int256)
    {
        return nodes[_node].feeDelta[_period];
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
        internal returns (MemoryNodeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, this.nodes.selector, 1, bytes32(uint256(_node)), 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get feeRateRange structure by delegatecall
    */
    function delegateGetFeeRateRange(address _target) internal returns (Range memory result) {
        bytes32 memoryAddress = delegateGetData(_target, this.feeRateRange.selector, 0, 0, 0);
        assembly {
            result := memoryAddress
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(uint64(delegateGet(_testTarget, this.resetTimestamp.selector)) == resetTimestamp);

        Range memory rangeToCheck = delegateGetFeeRateRange(_testTarget);
        require(feeRateRange.min == rangeToCheck.min &&
            feeRateRange.defaultValue == rangeToCheck.defaultValue &&
            feeRateRange.max == rangeToCheck.max);

        Policy storage policy = policies[RESERVED_POLICY_ID];
        Policy memory policyToCheck = delegateGetPolicy(_testTarget, RESERVED_POLICY_ID);
        require(policyToCheck.sponsor == policy.sponsor &&
            policyToCheck.owner == policy.owner &&
            policyToCheck.feeRate == policy.feeRate &&
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
        MemoryNodeInfo memory nodeInfoToCheck = delegateGetNodeInfo(_testTarget, RESERVED_NODE);
        require(nodeInfoToCheck.fee == nodeInfo.fee &&
            nodeInfoToCheck.feeRate == nodeInfo.feeRate &&
            nodeInfoToCheck.previousFeePeriod == nodeInfo.previousFeePeriod &&
            nodeInfoToCheck.minFeeRate == nodeInfo.minFeeRate);

        require(int256(delegateGet(_testTarget, this.getNodeFeeDelta.selector,
            bytes32(bytes20(RESERVED_NODE)), bytes32(uint256(11)))) == getNodeFeeDelta(RESERVED_NODE, 11));
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public override virtual {
        super.finishUpgrade(_target);

        if (resetTimestamp == 0) {
            resetTimestamp = uint64(block.timestamp);
        }

        // Create fake Policy and NodeInfo to use them in verifyState(address)
        Policy storage policy = policies[RESERVED_POLICY_ID];
        policy.sponsor = msg.sender;
        policy.owner = address(this);
        policy.startTimestamp = 1;
        policy.endTimestamp = 2;
        policy.feeRate = 3;
        policy.disabled = true;
        policy.arrangements.push(ArrangementInfo(RESERVED_NODE, 11, 22));
        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        nodeInfo.fee = 100;
        nodeInfo.feeRate = 33;
        nodeInfo.previousFeePeriod = 44;
        nodeInfo.feeDelta[11] = 55;
        nodeInfo.minFeeRate = 777;
    }
}
