// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "zeppelin/math/Math.sol";
import "zeppelin/utils/Address.sol";
import "contracts/lib/SignatureVerifier.sol";
import "zeppelin/ownership/Ownable.sol";


/**
* @title PolicyManager
* @notice Contract holds policy data and locks accrued policy fees
* @dev |v7.1.1|
*/
abstract contract PolicyManager is Ownable {
    using Address for address payable;

    event PolicyCreated(
        bytes16 indexed policyId,
        address indexed sponsor,
        address indexed owner,
        uint256 feePerSecond,
        uint64 startTimestamp,
        uint64 endTimestamp,
        uint256 numberOfoperators
    );
    event ArrangementRevoked(
        bytes16 indexed policyId,
        address indexed sender,
        address indexed operator,
        uint256 value
    );
    event RefundForArrangement(
        bytes16 indexed policyId,
        address indexed sender,
        address indexed operator,
        uint256 value
    );
    event PolicyRevoked(bytes16 indexed policyId, address indexed sender, uint256 value);
    event RefundForPolicy(bytes16 indexed policyId, address indexed sender, uint256 value);
    event MinFeeRateSet(address indexed operator, uint256 value);
    // TODO #1501
    // Range range
    event FeeRateRangeSet(address indexed sender, uint256 min, uint256 defaultValue, uint256 max);
    event Withdrawn(address indexed sender, address indexed operator, address indexed beneficiary, uint256 value);

    struct ArrangementInfo {
        bool arranged;
        uint256 paidFee;
        uint64 endTimestamp;
    }

    struct Policy {
        address payable sponsor;
        address owner;

        uint128 feePerSecond;
        uint64 startTimestamp;
        uint64 endTimestamp;
        uint256 operatorsLength;

//        uint256 reservedSlot1;
//        uint256 reservedSlot2;
//        uint256 reservedSlot3;
//        uint256 reservedSlot4;
//        uint256 reservedSlot5;

        mapping(address => ArrangementInfo) arrangements;
    }

    struct Range {
        uint128 min;
        uint128 defaultValue;
        uint128 max;
    }

    uint256 internal constant MAX_BALANCE = uint256(uint128(0) - 1);

    mapping (bytes16 => Policy) public policies;
    mapping (address => uint256) public operatorFeeRate;
    Range public feeRateRange;

    // TODO add slots

    /**
    * @notice Set minimum, default & maximum fee rate for all stakers and all policies ('global fee range')
    */
    // TODO # 1501
    // function setFeeRateRange(Range calldata _range) external onlyOwner {
    function setFeeRateRange(uint128 _min, uint128 _default, uint128 _max) external onlyOwner {
        require(_min <= _default && _default <= _max, "Incorrect range");
        feeRateRange = Range(_min, _default, _max);
        emit FeeRateRangeSet(msg.sender, _min, _default, _max);
    }

    /**
    * @notice Set the minimum acceptable fee rate
    * @dev Input value must fall within `feeRateRange` (global fee range)
    */
    function setMinFeeRate(uint256 _minFeeRate) external {
        require(_minFeeRate >= feeRateRange.min &&
            _minFeeRate <= feeRateRange.max,
            "The staker's min fee rate must fall within the global fee range");
        if (operatorFeeRate[msg.sender] == _minFeeRate) {
            return;
        }
        operatorFeeRate[msg.sender] = _minFeeRate; // TODO who can set this value?
        emit MinFeeRateSet(msg.sender, _minFeeRate);
    }

    /**
    * @notice Get the minimum acceptable fee rate
    */
    function getMinFeeRate(address _operator) public view returns (uint256) {
        uint256 minFeeRate = operatorFeeRate[_operator];
        // if minFeeRate has not been set or chosen value falls outside the global fee range
        // a default value is returned instead
        if (minFeeRate == 0 ||
            minFeeRate < feeRateRange.min ||
            minFeeRate > feeRateRange.max) {
            return feeRateRange.defaultValue;
        } else {
            return minFeeRate;
        }
    }

    /**
    * @notice Create policy
    * @dev Generate policy id before creation
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _endTimestamp End timestamp of the policy in seconds
    * @param _operators operators that will handle policy
    */
    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _endTimestamp,
        address[] calldata _operators
    )
        external payable
    {
        require(
            _endTimestamp > block.timestamp &&
            msg.value > 0,
            "Wrong input parameters"
        );

        require(address(this).balance <= MAX_BALANCE, "Balance overflow");
        uint256 duration = _endTimestamp - block.timestamp;

        uint128 feePerSecond = uint128(msg.value / _operators.length / duration);
        require(feePerSecond > 0 && feePerSecond * duration * _operators.length  == msg.value, "Wrong ETH value");

        Policy storage policy = createPolicy(_policyId, _policyOwner, _endTimestamp, feePerSecond, _operators.length);

        for (uint256 i = 0; i < _operators.length; i++) {
            address operator = _operators[i];
            require(operator != address(0) && isAuthorized(operator), "Operator has no authorized stake");
            policy.arrangements[operator].arranged = true;
        }
    }

    // TODO do we need wrapper for multiple policies?

    /**
    * @notice Create policy
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _endTimestamp End timestamp of the policy in seconds
    * @param _feePerSecond Fee rate for policy
    * @param _operatorsLength Number of operators that will handle policy
    */
    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _endTimestamp,
        uint128 _feePerSecond,
        uint256 _operatorsLength
    )
        internal returns (Policy storage policy)
    {
        policy = policies[_policyId];
        require(policy.feePerSecond == 0, "Policy id is in use");

        policy.sponsor = payable(msg.sender);
        policy.startTimestamp = uint64(block.timestamp);
        policy.endTimestamp = _endTimestamp;
        policy.feePerSecond = _feePerSecond;
        policy.operatorsLength = _operatorsLength;

        if (_policyOwner != msg.sender && _policyOwner != address(0)) {
            policy.owner = _policyOwner;
        }

        emit PolicyCreated(
            _policyId,
            msg.sender,
            _policyOwner == address(0) ? msg.sender : _policyOwner,
            _feePerSecond,
            policy.startTimestamp,
            policy.endTimestamp,
            policy.operatorsLength
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
    * @notice Withdraw fee by operator
    */
    function withdraw(bytes16 _policyId, address _operator) public returns (uint256) {
        Policy storage policy = policies[_policyId];

        ArrangementInfo storage arrangement = policy.arrangements[_operator];
        require(arrangement.arranged, "There is no active arrangement with the operator");
        uint64 endTimestamp = arrangement.endTimestamp != 0 ? arrangement.endTimestamp : policy.endTimestamp;
        uint256 passedTime = Math.min(endTimestamp, block.timestamp) - policy.startTimestamp;
        uint256 allFee = passedTime * policy.feePerSecond;

        uint256 fee = allFee - arrangement.paidFee;

        require(fee != 0, "Nothing to withdraw");
        address payable beneficiary = getBeneficiary(_operator);
        emit Withdrawn(msg.sender, _operator, beneficiary, fee);
        beneficiary.sendValue(fee);
        return fee;
    }

    /**
    * @notice Revoke policy by the sponsor
    * @param _policyId Policy id
    */
    function revokePolicy(bytes16 _policyId) external returns (uint256 refundValue) {
        require(getPolicyOwner(_policyId) == msg.sender, "Caller must be policy owner");
        return _revokePolicy(_policyId);
    }

    /**
    * @notice Revoke policy by the sponsor
    * @param _policyId Policy id
    */
    function _revokePolicy(bytes16 _policyId) internal returns (uint256 refundValue) {
        Policy storage policy = policies[_policyId];
        require(policy.endTimestamp > block.timestamp, "Policy already finished");
        refundValue = (policy.endTimestamp - block.timestamp) * policy.feePerSecond * policy.operatorsLength;
        policy.endTimestamp = uint64(block.timestamp);
        policy.operatorsLength = 0;
        emit PolicyRevoked(_policyId, msg.sender, refundValue);
        policy.sponsor.sendValue(refundValue);
    }

    /**
    * @notice Revoke arrangement by the sponsor
    * @param _policyId Policy id
    * @param _operator operator that will be excluded
    */
    function revokeArrangement(bytes16 _policyId, address _operator)
        external returns (uint256 refundValue)
    {
        require(_operator != address(0), "Operator must be specified");
        require(getPolicyOwner(_policyId) == msg.sender, "Caller must be policy owner");
        return _revokeArrangement(_policyId, _operator);
    }

    /**
    * @notice Revoke arrangement by the sponsor
    * @param _policyId Policy id
    * @param _operator operator that will be excluded
    */
    function _revokeArrangement(bytes16 _policyId, address _operator)
        internal returns (uint256 refundValue)
    {
        Policy storage policy = policies[_policyId];
        require(policy.endTimestamp > block.timestamp, "Policy already finished");
        ArrangementInfo storage arrangement = policy.arrangements[_operator];
        require(
            arrangement.arranged && arrangement.endTimestamp == 0,
            "There is no active arrangement with the operator"
        );
        refundValue = (policy.endTimestamp - block.timestamp) * policy.feePerSecond;
        arrangement.endTimestamp = uint64(block.timestamp);
        policy.operatorsLength -= 1;
        emit ArrangementRevoked(_policyId, msg.sender, _operator, refundValue);
        policy.sponsor.sendValue(refundValue);
    }

    /**
    * @notice Get unsigned hash for revocation
    * @param _policyId Policy id
    * @param _operator operator that will be excluded
    * @return Revocation hash, EIP191 version 0x45 ('E')
    */
    function getRevocationHash(bytes16 _policyId, address _operator) public view returns (bytes32) {
        return SignatureVerifier.hashEIP191(abi.encodePacked(_policyId, _operator), bytes1(0x45));
    }

    /**
    * @notice Check correctness of signature
    * @param _policyId Policy id
    * @param _operator operator that will be excluded, zero address if whole policy will be revoked
    * @param _signature Signature of owner
    */
    function checkOwnerSignature(bytes16 _policyId, address _operator, bytes memory _signature) internal view {
        bytes32 hash = getRevocationHash(_policyId, _operator);
        address recovered = SignatureVerifier.recover(hash, _signature);
        require(getPolicyOwner(_policyId) == recovered, "Signer must be policy owner");
    }

    /**
    * @notice Revoke policy or arrangement using owner's signature
    * @param _policyId Policy id
    * @param _operator operator that will be excluded, zero address if whole policy will be revoked
    * @param _signature Signature of owner, EIP191 version 0x45 ('E')
    */
    function revoke(bytes16 _policyId, address _operator, bytes calldata _signature)
        external returns (uint256 refundValue)
    {
        checkOwnerSignature(_policyId, _operator, _signature);
        refundValue = _operator == address(0) ? _revokePolicy(_policyId) : _revokeArrangement(_policyId, _operator);
    }

    /**
    * @notice Returns beneficiary related to the operator
    */
    function getBeneficiary(address) internal virtual view returns (address payable);

    /**
    * @notice Returns true if operator has authorized stake to this application
    */
    function isAuthorized(address) internal virtual view returns (bool);

    /**
    * @notice Return the information about arrangement
    */
    function getArrangementInfo(bytes16 _policyId, address _operator)
    // TODO change to structure when ABIEncoderV2 is released (#1501)
//        public view returns (ArrangementInfo)
        external view returns (bool arranged, uint256 paidFee, uint64 endTimestamp)
    {
        ArrangementInfo storage arrangement = policies[_policyId].arrangements[_operator];
        arranged = arrangement.arranged;
        paidFee = arrangement.paidFee;
        endTimestamp = arrangement.endTimestamp;
    }

//
//    /**
//    * @dev Get Policy structure by delegatecall
//    */
//    function delegateGetPolicy(address _target, bytes16 _policyId)
//        internal returns (Policy memory result)
//    {
//        bytes32 memoryAddress = delegateGetData(_target, this.policies.selector, 1, bytes32(_policyId), 0);
//        assembly {
//            result := memoryAddress
//        }
//    }
//
//    /**
//    * @dev Get ArrangementInfo structure by delegatecall
//    */
//    function delegateGetArrangementInfo(address _target, bytes16 _policyId, uint256 _index)
//        internal returns (ArrangementInfo memory result)
//    {
//        bytes32 memoryAddress = delegateGetData(
//            _target, this.getArrangementInfo.selector, 2, bytes32(_policyId), bytes32(_index));
//        assembly {
//            result := memoryAddress
//        }
//    }
//
//    /**
//    * @dev Get operatorInfo structure by delegatecall
//    */
//    function delegateGetoperatorInfo(address _target, address _operator)
//        internal returns (MemoryoperatorInfo memory result)
//    {
//        bytes32 memoryAddress = delegateGetData(_target, this.operators.selector, 1, bytes32(uint256(uint160(_operator))), 0);
//        assembly {
//            result := memoryAddress
//        }
//    }
//
//    /**
//    * @dev Get feeRateRange structure by delegatecall
//    */
//    function delegateGetFeeRateRange(address _target) internal returns (Range memory result) {
//        bytes32 memoryAddress = delegateGetData(_target, this.feeRateRange.selector, 0, 0, 0);
//        assembly {
//            result := memoryAddress
//        }
//    }

//    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
//    function verifyState(address _testTarget) public override virtual {
//        super.verifyState(_testTarget);
////        require(uint64(delegateGet(_testTarget, this.resetTimestamp.selector)) == resetTimestamp);
////
////        Range memory rangeToCheck = delegateGetFeeRateRange(_testTarget);
////        require(feeRateRange.min == rangeToCheck.min &&
////            feeRateRange.defaultValue == rangeToCheck.defaultValue &&
////            feeRateRange.max == rangeToCheck.max);
////
////        Policy storage policy = policies[RESERVED_POLICY_ID];
////        Policy memory policyToCheck = delegateGetPolicy(_testTarget, RESERVED_POLICY_ID);
////        require(policyToCheck.sponsor == policy.sponsor &&
////            policyToCheck.owner == policy.owner &&
////            policyToCheck.feeRate == policy.feeRate &&
////            policyToCheck.startTimestamp == policy.startTimestamp &&
////            policyToCheck.endTimestamp == policy.endTimestamp &&
////            policyToCheck.disabled == policy.disabled);
////
////        require(delegateGet(_testTarget, this.getArrangementsLength.selector, RESERVED_POLICY_ID) ==
////            policy.arrangements.length);
////        if (policy.arrangements.length > 0) {
////            ArrangementInfo storage arrangement = policy.arrangements[0];
////            ArrangementInfo memory arrangementToCheck = delegateGetArrangementInfo(
////                _testTarget, RESERVED_POLICY_ID, 0);
////            require(arrangementToCheck.operator == arrangement.operator &&
////                arrangementToCheck.indexOfDowntimePeriods == arrangement.indexOfDowntimePeriods &&
////                arrangementToCheck.lastRefundedPeriod == arrangement.lastRefundedPeriod);
////        }
////
////        operatorInfo storage operatorInfo = operators[RESERVED_operator];
////        MemoryoperatorInfo memory operatorInfoToCheck = delegateGetoperatorInfo(_testTarget, RESERVED_operator);
////        require(operatorInfoToCheck.fee == operatorInfo.fee &&
////            operatorInfoToCheck.feeRate == operatorInfo.feeRate &&
////            operatorInfoToCheck.previousFeePeriod == operatorInfo.previousFeePeriod &&
////            operatorInfoToCheck.minFeeRate == operatorInfo.minFeeRate);
////
////        require(int256(delegateGet(_testTarget, this.getoperatorFeeDelta.selector,
////            bytes32(bytes20(RESERVED_operator)), bytes32(uint256(11)))) == getoperatorFeeDelta(RESERVED_operator, 11));
//    }
//
//    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
//    function finishUpgrade(address _target) public override virtual {
//        super.finishUpgrade(_target);
//
////        if (resetTimestamp == 0) {
////            resetTimestamp = uint64(block.timestamp);
////        }
////
////        // Create fake Policy and operatorInfo to use them in verifyState(address)
////        Policy storage policy = policies[RESERVED_POLICY_ID];
////        policy.sponsor = msg.sender;
////        policy.owner = address(this);
////        policy.startTimestamp = 1;
////        policy.endTimestamp = 2;
////        policy.feeRate = 3;
////        policy.disabled = true;
////        policy.arrangements.push(ArrangementInfo(RESERVED_operator, 11, 22));
////        operatorInfo storage operatorInfo = operators[RESERVED_operator];
////        operatorInfo.fee = 100;
////        operatorInfo.feeRate = 33;
////        operatorInfo.previousFeePeriod = 44;
////        operatorInfo.feeDelta[11] = 55;
////        operatorInfo.minFeeRate = 777;
//    }
}
