// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

contract SubscriptionManager {

    uint256 private constant RATE_PER_DAY = 50 gwei;
    uint256 public constant RATE_PER_SECOND = RATE_PER_DAY / 1 days;

    struct Policy { // TODO: Optimize struct layout
        address payable sponsor;
        address owner;
        uint64 startTimestamp;
        uint64 endTimestamp;
    }

    event PolicyCreated(
        bytes16 indexed policyId,
        address indexed sponsor,
        address indexed owner,
        uint64 startTimestamp,
        uint64 endTimestamp
    );
    
    address payable public owner;
    mapping (bytes16 => Policy) public policies;

    constructor(){
        owner = payable(msg.sender);
    }

    function createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _startTimestamp,
        uint64 _endTimestamp
    )
        external payable
    {
        require(
            _startTimestamp < _endTimestamp &&
            block.timestamp < _endTimestamp,
            "Invalid timestamps"
        );
        uint64 duration = _endTimestamp - _startTimestamp;
        require(
            duration > 0 &&
            msg.value == RATE_PER_SECOND * uint64(duration)
        );
        //Policy storage policy = 
        _createPolicy(_policyId, _policyOwner, _startTimestamp, _endTimestamp);
    }

    /**
    * @notice Create policy
    * @param _policyId Policy id
    * @param _policyOwner Policy owner. Zero address means sender is owner
    * @param _startTimestamp Start timestamp of the policy in seconds
    * @param _endTimestamp End timestamp of the policy in seconds
    */
    function _createPolicy(
        bytes16 _policyId,
        address _policyOwner,
        uint64 _startTimestamp,
        uint64 _endTimestamp
    )
        internal returns (Policy storage policy)
    {
        policy = policies[_policyId];
        require(
            policy.endTimestamp < block.timestamp,
            "Policy is currently active"
        );

        policy.sponsor = payable(msg.sender);
        policy.startTimestamp = _startTimestamp;
        policy.endTimestamp = _endTimestamp;

        if (_policyOwner != msg.sender && _policyOwner != address(0)) {
            policy.owner = _policyOwner;
        }

        emit PolicyCreated(
            _policyId,
            msg.sender,
            _policyOwner == address(0) ? msg.sender : _policyOwner,
            _startTimestamp,
            _endTimestamp
        );
    }

    function isPolicyActive(bytes16 _policyID) public view returns(bool){
        return policies[_policyID].endTimestamp > block.timestamp;
    }

    function sweep(address payable recipient) external {
        require(msg.sender == owner);
        uint256 balance = address(this).balance;
        (bool sent, ) = recipient.call{value: balance}("");
        require(sent, "Failed transfer");
    }

}
