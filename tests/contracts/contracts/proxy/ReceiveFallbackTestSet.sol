// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/proxy/Upgradeable.sol";


/**
* @dev Contract can't handle 'receive' and 'fallback' requests
*/
contract NoFallback is Upgradeable {}


/**
* @dev Contract can handle only 'receive' requests
*/
contract OnlyReceive is NoFallback {

    uint256 public receiveRequests;
    uint256 public value;

    receive() external payable {
        receiveRequests += 1;
        value += msg.value;
    }

}


/**
* @dev Contract can handle 'receive' and 'fallback' requests
*/
contract ReceiveFallback is OnlyReceive {

    uint256 public fallbackRequests;

    fallback() external payable {
        fallbackRequests += 1;
        value += msg.value;
    }

}
