// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/access/AccessControlUpgradeable.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";

contract SubscriptionManager is Initializable, AccessControlUpgradeable {

    bytes32 public constant SET_RATE_ROLE =
        keccak256("Power to set the fee rate");
    bytes32 public constant WITHDRAW_ROLE =
        keccak256("Power to withdraw funds from SubscriptionManager");

    // The layout of policy struct is optimized, so sponsor, timestamps and size
    // fit in a single 256-word.
    struct Policy {
        address payable sponsor;
        uint32 startTimestamp;
        uint32 endTimestamp;
        uint16 size; // also known as `N`
        // There's still 2 bytes available here
        address owner;
    }

    event PolicyCreated(
        bytes16 indexed policyId,
        address indexed sponsor,
        address indexed owner,
        uint16 size,
        uint32 startTimestamp,
        uint32 endTimestamp,
        uint256 cost
    );

    event FeeRateUpdated(uint256 oldFeeRate, uint256 newFeeRate);

    // Per-second, per-node service fee rate
    uint256 public feeRate;

    // Mapping that stores policy structs, keyed by policy ID
    mapping (bytes16 => Policy) internal _policies;

    function initialize(uint256 _feeRate) public initializer {
        _setFeeRate(_feeRate);
        _setupRole(SET_RATE_ROLE, msg.sender);
        _setupRole(WITHDRAW_ROLE, msg.sender);
        _setupRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    function getPolicyCost(
        uint16 _size,
        uint32 _startTimestamp,
        uint32 _endTimestamp
    ) public view returns (uint256){
        uint32 duration = _endTimestamp - _startTimestamp;
        require(duration > 0, "Invalid timestamps");
        require(_size > 0, "Invalid policy size");
        return feeRate * _size * duration;
    }

    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint16 _size,
        uint32 _startTimestamp,
        uint32 _endTimestamp
    )
        external payable
    {
        require(
            _startTimestamp < _endTimestamp && block.timestamp < _endTimestamp,
            "Invalid timestamps"
        );
        require(
            msg.value == getPolicyCost(_size, _startTimestamp, _endTimestamp),
            "Invalid policy cost"
        );

        _createPolicy(_policyId, _policyOwner, _size, _startTimestamp, _endTimestamp);
    }

    /**
    * @notice Create policy
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _size Number of nodes involved in the policy
    * @param _startTimestamp Start timestamp of the policy in seconds
    * @param _endTimestamp End timestamp of the policy in seconds
    */
    function _createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint16 _size,
        uint32 _startTimestamp,
        uint32 _endTimestamp
    )
        internal returns (Policy storage policy)
    {
        policy = _policies[_policyId];
        require(
            policy.endTimestamp < block.timestamp,
            "Policy is currently active"
        );

        policy.sponsor = payable(msg.sender);
        policy.startTimestamp = _startTimestamp;
        policy.endTimestamp = _endTimestamp;
        policy.size = _size;

        if (_policyOwner != msg.sender && _policyOwner != address(0)) {
            policy.owner = _policyOwner;
        }

        emit PolicyCreated(
            _policyId,
            msg.sender,
            _policyOwner == address(0) ? msg.sender : _policyOwner,
            _size,
            _startTimestamp,
            _endTimestamp,
            msg.value
        );
    }

    function getPolicy(bytes16 _policyID) public view returns(Policy memory){
        return _policies[_policyID];
    }

    function isPolicyActive(bytes16 _policyID) public view returns(bool){
        return _policies[_policyID].endTimestamp > block.timestamp;
    }

    function _setFeeRate(uint256 newFee) internal {
        uint256 oldFee = feeRate;
        feeRate = newFee;
        emit FeeRateUpdated(oldFee, newFee);
    }

    function setFeeRate(uint256 _ratePerSecond) onlyRole(SET_RATE_ROLE) external {
        _setFeeRate(_ratePerSecond);
    }

    function sweep(address payable recipient) onlyRole(WITHDRAW_ROLE) external {
        uint256 balance = address(this).balance;
        (bool sent, ) = recipient.call{value: balance}("");
        require(sent, "Failed transfer");
    }

}
