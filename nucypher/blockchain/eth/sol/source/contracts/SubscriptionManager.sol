// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "../zeppelin/proxy/Initializable.sol";

contract SubscriptionManager is Initializable {

    // The layout of policy struct is optimized, so sponsor, timestamps and size
    // fit in a single 256-word.
    struct Policy {
        address payable sponsor;
        uint32 startTimestamp;
        uint32 endTimestamp;
        uint16 size; // also known as `N`
        address owner;
    }

    event PolicyCreated(
        bytes16 indexed policyId,
        address indexed sponsor,
        address indexed owner,
        uint16 size,
        uint32 startTimestamp,
        uint32 endTimestamp
    );

    event FeeRateUpdated(uint256 oldFeeRate, uint256 newFeeRate);

    // Per-second service fee rate
    uint256 public feeRate;

    // Mapping that stores policy structs, keyed by policy ID
    mapping (bytes16 => Policy) internal _policies;

    function initialize(uint256 _feeRate) public initializer {
        _setFeeRate(_feeRate);
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
            _startTimestamp < _endTimestamp &&
            block.timestamp < _endTimestamp,
            "Invalid timestamps"
        );
        uint32 duration = _endTimestamp - _startTimestamp;
        require(
            duration > 0 && _size > 0 &&
            msg.value == feeRate * _size * uint32(duration)
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
            _endTimestamp
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

    function setFeeRate(uint256 _rate_per_second) external {
        _setFeeRate(_rate_per_second);
    }

    function sweep(address payable recipient) external {
        uint256 balance = address(this).balance;
        (bool sent, ) = recipient.call{value: balance}("");
        require(sent, "Failed transfer");
    }

}