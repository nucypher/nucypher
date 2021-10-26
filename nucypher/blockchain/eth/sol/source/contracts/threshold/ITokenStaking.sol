// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
* @notice TokenStaking interface
*/
interface ITokenStaking {
    enum StakingProvider {NU, KEEP, T}

    function stakedNu(address) external view returns (uint256);
    function ownerOf(address) external view returns (address);
    function beneficiaryOf(address) external view returns (address payable);
    function approveAuthorizationDecrease(address) external;
    function getMinStaked(address, StakingProvider) external view returns (uint96);
    function authorizedStake(address operator, address application) external view returns (uint96);
    function stakes(address operator) external view returns (uint96 tStake, uint96 keepInTStake, uint96 nuInTStake);
    function seize(
        uint96 _amount,
        uint256 _rewardMultiplier,
        address _notifier,
        address[] memory _operators
    ) external;
}
