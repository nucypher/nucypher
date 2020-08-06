// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


/**
* @notice Contract for using in token tests
*/
contract ReceiveApprovalMethodMock {

    address public sender;
    uint256 public value;
    address public tokenContract;
    bytes public extraData;

    function receiveApproval(
        address _from,
        uint256 _value,
        address _tokenContract,
        bytes calldata _extraData
    )
        external
    {
        sender = _from;
        value = _value;
        tokenContract = _tokenContract;
        extraData = _extraData;
    }

}
