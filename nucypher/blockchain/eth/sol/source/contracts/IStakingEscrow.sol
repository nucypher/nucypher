// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "contracts/NuCypherToken.sol";

interface IStakingEscrow {
    function token() external view returns (NuCypherToken);
    function secondsPerPeriod() external view returns (uint32);
    function stakerFromWorker(address) external view returns (address);
    function getAllTokens(address) external view returns (uint256);
    function slashStaker(address, uint256, address, uint256) external;
    function genesisSecondsPerPeriod() external view returns (uint32);
    function getPastDowntimeLength(address) external view returns (uint256);
    function findIndexOfPastDowntime(address, uint16) external view returns (uint256);
    function getPastDowntime(address, uint256) external view returns (uint16, uint16);
    function getLastCommittedPeriod(address) external view returns (uint16);
    function minLockedPeriods() external view returns (uint16);
    function maxAllowableLockedTokens() external view returns (uint256);
    function minAllowableLockedTokens() external view returns (uint256);
    function getCompletedWork(address) external view returns (uint256);
    function depositFromWorkLock(address, uint256, uint16) external;
    function setWorkMeasurement(address, bool) external returns (uint256);
    function setSnapshots(bool _enableSnapshots) external;
    function withdraw(uint256 _value) external;
}
