// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity ^0.7.0;

interface IForwarder {

    function isForwarder() external pure returns (bool);
    function canForward(address sender, bytes calldata evmCallScript) external view returns (bool);
    function forward(bytes calldata evmCallScript) external;
    
}
