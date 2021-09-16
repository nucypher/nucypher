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
        uint256 numberOfWorkers
    );
    event ArrangementRevoked(
        bytes16 indexed policyId,
        address indexed sender,
        address indexed worker,
        uint256 value
    );
    event RefundForArrangement(
        bytes16 indexed policyId,
        address indexed sender,
        address indexed worker,
        uint256 value
    );
    event PolicyRevoked(bytes16 indexed policyId, address indexed sender, uint256 value);
    event RefundForPolicy(bytes16 indexed policyId, address indexed sender, uint256 value);
    event MinFeeRateSet(address indexed worker, uint256 value);
    // TODO #1501
    // Range range
    event FeeRateRangeSet(address indexed sender, uint256 min, uint256 defaultValue, uint256 max);
    event Withdrawn(address indexed sender, address indexed worker, address indexed beneficiary, uint256 value);

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
        uint256 workersLength;

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
    mapping (address => uint256) public workerFeeRate;
    Range public feeRateRange;

    // TODO add slots

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
    * @notice Set the minimum acceptable fee rate
    * @dev Input value must fall within `feeRateRange` (global fee range)
    */
    function setMinFeeRate(uint256 _minFeeRate) external {
        require(_minFeeRate >= feeRateRange.min &&
            _minFeeRate <= feeRateRange.max,
            "The staker's min fee rate must fall within the global fee range");
        if (workerFeeRate[msg.sender] == _minFeeRate) {
            return;
        }
        workerFeeRate[msg.sender] = _minFeeRate; // TODO who can set this value?
        emit MinFeeRateSet(msg.sender, _minFeeRate);
    }

    /**
    * @notice Get the minimum acceptable fee rate
    */
    function getMinFeeRate(address _worker) public view returns (uint256) {
        uint256 minFeeRate = workerFeeRate[_worker];
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
    * @param _workers Workers that will handle policy
    */
    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _endTimestamp,
        address[] calldata _workers
    )
        external payable
    {
        require(
            _endTimestamp > block.timestamp &&
            msg.value > 0
        );

        require(address(this).balance <= MAX_BALANCE);
        uint256 duration = _endTimestamp - block.timestamp;

        uint128 feePerSecond = uint128(msg.value / _workers.length / duration);
        require(feePerSecond > 0 && feePerSecond * duration * _workers.length  == msg.value);

        Policy storage policy = createPolicy(_policyId, _policyOwner, _endTimestamp, feePerSecond, _workers.length);

        for (uint256 i = 0; i < _workers.length; i++) {
            address worker = _workers[i];
            require(worker != address(0) && isAuthorized(worker));
            policy.arrangements[worker].arranged = true;
        }
    }


    // TODO ?
//    /**
//    * @notice Create multiple policies with the same owner, workers and length
//    * @dev Generate policy ids before creation
//    * @param _policyIds Policy ids
//    * @param _policyOwner Policy owner. Zero address means sender is owner
//    * @param _endTimestamp End timestamp of all policies in seconds
//    * @param _workers Workers that will handle all policies
//    */
//    function createPolicies(
//        bytes16[] calldata _policyIds,
//        address _policyOwner,
//        uint64 _endTimestamp,
//        address[] calldata _workers
//    )
//        external payable
//    {
//        require(
//            _endTimestamp > block.timestamp &&
//            msg.value > 0 &&
//            _policyIds.length > 1
//        );
//
//        require(address(this).balance <= MAX_BALANCE);
//        uint16 currentPeriod = getCurrentPeriod();
//        uint16 endPeriod = uint16(_endTimestamp / secondsPerPeriod) + 1;
//        uint256 numberOfPeriods = endPeriod - currentPeriod;
//
//        uint128 feeRate = uint128(msg.value.div(_workers.length) / numberOfPeriods / _policyIds.length);
//        require(feeRate > 0 && feeRate * numberOfPeriods * _workers.length * _policyIds.length == msg.value);
//
//        for (uint256 i = 0; i < _policyIds.length; i++) {
//            Policy storage policy = createPolicy(_policyIds[i], _policyOwner, _endTimestamp, feeRate, _workers.length);
//
//            for (uint256 j = 0; j < _workers.length; j++) {
//                policy.arrangements.push(ArrangementInfo(_workers[j], 0, 0));
//            }
//        }
//
//        int256 fee = int256(_policyIds.length * feeRate);
//
//        for (uint256 i = 0; i < _workers.length; i++) {
//            address worker = _workers[i];
//            addFeeToWorker(currentPeriod, endPeriod, worker, feeRate, fee);
//        }
//    }

    /**
    * @notice Create policy
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _endTimestamp End timestamp of the policy in seconds
    * @param _feePerSecond Fee rate for policy
    * @param _workersLength Number of workers that will handle policy
    */
    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _endTimestamp,
        uint128 _feePerSecond,
        uint256 _workersLength
    )
        internal returns (Policy storage policy)
    {
        policy = policies[_policyId];
        require(policy.feePerSecond == 0);

        policy.sponsor = payable(msg.sender);
        policy.startTimestamp = uint64(block.timestamp);
        policy.endTimestamp = _endTimestamp;
        policy.feePerSecond = _feePerSecond;
        policy.workersLength = _workersLength;

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
            policy.workersLength
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
    * @notice Withdraw fee by worker
    */
    function withdraw(bytes16 _policyId, address _worker) public returns (uint256) {
        Policy storage policy = policies[_policyId];

        ArrangementInfo storage arrangement = policy.arrangements[_worker];
        require(arrangement.arranged);
        uint64 endTimestamp = arrangement.endTimestamp != 0 ? arrangement.endTimestamp : policy.endTimestamp;
        uint256 passedTime = Math.min(endTimestamp, block.timestamp) - policy.startTimestamp;
        uint256 allFee = passedTime * policy.feePerSecond;

        uint256 fee = allFee - arrangement.paidFee;

        require(fee != 0);
        address payable beneficiary = getBeneficiary(_worker);
        emit Withdrawn(msg.sender, _worker, beneficiary, fee);
        beneficiary.sendValue(fee);
        return fee;
    }

    /**
    * @notice Revoke policy by the sponsor
    * @param _policyId Policy id
    */
    function revokePolicy(bytes16 _policyId) external returns (uint256 refundValue) {
        require(getPolicyOwner(_policyId) == msg.sender);
        return _revokePolicy(_policyId);
    }

    /**
    * @notice Revoke policy by the sponsor
    * @param _policyId Policy id
    */
    function _revokePolicy(bytes16 _policyId) internal returns (uint256 refundValue) {
        Policy storage policy = policies[_policyId];
        require(policy.endTimestamp > block.timestamp);
        refundValue = (policy.endTimestamp - block.timestamp) * policy.feePerSecond * policy.workersLength;
        policy.endTimestamp = uint64(block.timestamp);
        policy.workersLength = 0;
        emit PolicyRevoked(_policyId, msg.sender, refundValue);
        policy.sponsor.sendValue(refundValue);
    }

    /**
    * @notice Revoke arrangement by the sponsor
    * @param _policyId Policy id
    * @param _worker Worker that will be excluded
    */
    function revokeArrangement(bytes16 _policyId, address _worker)
        external returns (uint256 refundValue)
    {
        require(_worker != address(0));
        require(getPolicyOwner(_policyId) == msg.sender);
        return _revokeArrangement(_policyId, _worker);
    }

    /**
    * @notice Revoke arrangement by the sponsor
    * @param _policyId Policy id
    * @param _worker Worker that will be excluded
    */
    function _revokeArrangement(bytes16 _policyId, address _worker)
        internal returns (uint256 refundValue)
    {
        Policy storage policy = policies[_policyId];
        require(policy.endTimestamp > block.timestamp);
        ArrangementInfo storage arrangement = policy.arrangements[_worker];
        require(arrangement.arranged && arrangement.endTimestamp == 0);
        refundValue = (policy.endTimestamp - block.timestamp) * policy.feePerSecond;
        arrangement.endTimestamp = uint64(block.timestamp);
        policy.workersLength -= 1;
        emit ArrangementRevoked(_policyId, msg.sender, _worker, refundValue);
        policy.sponsor.sendValue(refundValue);
    }

    /**
    * @notice Get unsigned hash for revocation
    * @param _policyId Policy id
    * @param _worker Worker that will be excluded
    * @return Revocation hash, EIP191 version 0x45 ('E')
    */
    function getRevocationHash(bytes16 _policyId, address _worker) public view returns (bytes32) {
        return SignatureVerifier.hashEIP191(abi.encodePacked(_policyId, _worker), bytes1(0x45));
    }

    /**
    * @notice Check correctness of signature
    * @param _policyId Policy id
    * @param _worker Worker that will be excluded, zero address if whole policy will be revoked
    * @param _signature Signature of owner
    */
    function checkOwnerSignature(bytes16 _policyId, address _worker, bytes memory _signature) internal view {
        bytes32 hash = getRevocationHash(_policyId, _worker);
        address recovered = SignatureVerifier.recover(hash, _signature);
        require(getPolicyOwner(_policyId) == recovered);
    }

    /**
    * @notice Revoke policy or arrangement using owner's signature
    * @param _policyId Policy id
    * @param _worker Worker that will be excluded, zero address if whole policy will be revoked
    * @param _signature Signature of owner, EIP191 version 0x45 ('E')
    */
    function revoke(bytes16 _policyId, address _worker, bytes calldata _signature)
        external returns (uint256 refundValue)
    {
        checkOwnerSignature(_policyId, _worker, _signature);
        refundValue = _worker == address(0) ? _revokePolicy(_policyId) : _revokeArrangement(_policyId, _worker);
    }

    // TODO docs
    function getBeneficiary(address) internal virtual view returns (address payable);

    // TODO docs
    function isAuthorized(address) internal virtual view returns (bool);

    /**
    * @notice Return the information about arrangement
    */
    function getArrangementInfo(bytes16 _policyId, address _worker)
    // TODO change to structure when ABIEncoderV2 is released (#1501)
//        public view returns (ArrangementInfo)
        external view returns (bool arranged, uint256 paidFee, uint64 endTimestamp)
    {
        ArrangementInfo storage arrangement = policies[_policyId].arrangements[_worker];
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
//    * @dev Get WorkerInfo structure by delegatecall
//    */
//    function delegateGetWorkerInfo(address _target, address _worker)
//        internal returns (MemoryWorkerInfo memory result)
//    {
//        bytes32 memoryAddress = delegateGetData(_target, this.workers.selector, 1, bytes32(uint256(uint160(_worker))), 0);
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
////            require(arrangementToCheck.worker == arrangement.worker &&
////                arrangementToCheck.indexOfDowntimePeriods == arrangement.indexOfDowntimePeriods &&
////                arrangementToCheck.lastRefundedPeriod == arrangement.lastRefundedPeriod);
////        }
////
////        WorkerInfo storage workerInfo = workers[RESERVED_WORKER];
////        MemoryWorkerInfo memory workerInfoToCheck = delegateGetWorkerInfo(_testTarget, RESERVED_WORKER);
////        require(workerInfoToCheck.fee == workerInfo.fee &&
////            workerInfoToCheck.feeRate == workerInfo.feeRate &&
////            workerInfoToCheck.previousFeePeriod == workerInfo.previousFeePeriod &&
////            workerInfoToCheck.minFeeRate == workerInfo.minFeeRate);
////
////        require(int256(delegateGet(_testTarget, this.getWorkerFeeDelta.selector,
////            bytes32(bytes20(RESERVED_WORKER)), bytes32(uint256(11)))) == getWorkerFeeDelta(RESERVED_WORKER, 11));
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
////        // Create fake Policy and WorkerInfo to use them in verifyState(address)
////        Policy storage policy = policies[RESERVED_POLICY_ID];
////        policy.sponsor = msg.sender;
////        policy.owner = address(this);
////        policy.startTimestamp = 1;
////        policy.endTimestamp = 2;
////        policy.feeRate = 3;
////        policy.disabled = true;
////        policy.arrangements.push(ArrangementInfo(RESERVED_WORKER, 11, 22));
////        WorkerInfo storage workerInfo = workers[RESERVED_WORKER];
////        workerInfo.fee = 100;
////        workerInfo.feeRate = 33;
////        workerInfo.previousFeePeriod = 44;
////        workerInfo.feeDelta[11] = 55;
////        workerInfo.minFeeRate = 777;
//    }
}
