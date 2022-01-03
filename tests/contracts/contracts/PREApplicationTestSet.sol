// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "contracts/SimplePREApplication.sol";
//import "zeppelin/token/ERC20/ERC20.sol";
//import "zeppelin/token/ERC20/ERC20Detailed.sol";


///**
//* @notice Contract for testing PRE application contract
//*/
//contract TToken is ERC20, ERC20Detailed('T', 'T', 18) {
//
//    constructor (uint256 _totalSupplyOfTokens) {
//        _mint(msg.sender, _totalSupplyOfTokens);
//    }
//
//}


/**
* @notice Contract for testing PRE application contract
*/
contract ThresholdStakingForPREApplicationMock {

    struct OperatorInfo {
        address owner;
        address payable beneficiary;
        address authorizer;
        uint96 tStake;
        uint96 keepInTStake;
        uint96 nuInTStake;
    }

    SimplePREApplication public preApplication;

    mapping (address => OperatorInfo) public operatorInfo;

    function setApplication(SimplePREApplication _preApplication) external {
        preApplication = _preApplication;
    }

    function setRoles(
        address _operator,
        address _owner,
        address payable _beneficiary,
        address _authorizer
    )
        external
    {
        OperatorInfo storage info = operatorInfo[_operator];
        info.owner = _owner;
        info.beneficiary = _beneficiary;
        info.authorizer = _authorizer;
    }

    function setRoles(address _operator) external {
        OperatorInfo storage info = operatorInfo[_operator];
        info.owner = _operator;
        info.beneficiary = payable(_operator);
        info.authorizer = _operator;
    }

    function setStakes(
        address _operator,
        uint96 _tStake,
        uint96 _keepInTStake,
        uint96 _nuInTStake
    )
        external
    {
        OperatorInfo storage info = operatorInfo[_operator];
        info.tStake = _tStake;
        info.keepInTStake = _keepInTStake;
        info.nuInTStake = _nuInTStake;
    }

    function authorizedStake(address _operator, address _application) external view returns (uint96) {
        return 0;
    }

    function stakes(address _operator) external view returns (
        uint96 tStake,
        uint96 keepInTStake,
        uint96 nuInTStake
    ) {
        OperatorInfo storage info = operatorInfo[_operator];
        tStake = info.tStake;
        keepInTStake = info.keepInTStake;
        nuInTStake = info.nuInTStake;
    }

    function rolesOf(address _operator) external view returns (
        address owner,
        address payable beneficiary,
        address authorizer
    ) {
        OperatorInfo storage info = operatorInfo[_operator];
        owner = info.owner;
        beneficiary = info.beneficiary;
        authorizer = info.authorizer;
    }

//    function approveAuthorizationDecrease(address _operator) external returns (uint96) {
//
//    }

//    function seize(
//        uint96 _amount,
//        uint256 _rewardMultipier,
//        address _notifier,
//        address[] memory _operators
//    ) external {
//
//    }

//    function authorizationIncreased(address _operator, uint96 _fromAmount, uint96 _toAmount) external {
//        preApplication.authorizationIncreased(_operator, _fromAmount, _toAmount);
//    }

}


/**
* @notice Intermediary contract for testing worker
*/
contract Intermediary {

    SimplePREApplication immutable preApplication;

    constructor(SimplePREApplication _preApplication) {
        preApplication = _preApplication;
    }

    function bondWorker(address _worker) external {
        preApplication.bondWorker(_worker);
    }

    function confirmWorkerAddress() external {
        preApplication.confirmWorkerAddress();
    }

}
