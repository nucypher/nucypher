// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity ^0.8.0;

/// @title Interface of Threshold Network staking contract
/// @notice The staking contract enables T owners to have their wallets offline
///         and their stake operated by operators on their behalf. All off-chain
///         client software should be able to run without exposing operator’s
///         private key and should not require any owner’s keys at all.
///         The stake delegation optimizes the network throughput without
///         compromising the security of the owners’ stake.
interface IStaking {
    enum StakeType {
        NU,
        KEEP,
        T
    }

    //
    //
    // Delegating a stake
    //
    //

    /// @notice Creates a delegation with `msg.sender` owner with the given
    ///         operator, beneficiary, and authorizer. Transfers the given
    ///         amount of T to the staking contract.
    /// @dev The owner of the delegation needs to have the amount approved to
    ///      transfer to the staking contract.
    function stake(
        address operator,
        address payable beneficiary,
        address authorizer,
        uint96 amount
    ) external;

    /// @notice Copies delegation from the legacy KEEP staking contract to T
    ///         staking contract. No tokens are transferred. Caches the active
    ///         stake amount from KEEP staking contract. Can be called by
    ///         anyone.
    function stakeKeep(address operator) external;

    /// @notice Copies delegation from the legacy NU staking contract to T
    ///         staking contract, additionally appointing beneficiary and
    ///         authorizer roles. Caches the amount staked in NU staking
    ///         contract. Can be called only by the original delegation owner.
    function stakeNu(
        address operator,
        address payable beneficiary,
        address authorizer
    ) external;

    /// @notice Refresh Keep stake owner. Can be called only by the old owner.
    function refreshKeepStakeOwner(address operator) external;

    /// @notice Allows the Governance to set the minimum required stake amount.
    ///         This amount is required to protect against griefing the staking
    ///         contract and individual applications are allowed to require
    ///         higher minimum stakes if necessary.
    function setMinimumStakeAmount(uint96 amount) external;

    //
    //
    // Authorizing an application
    //
    //

    /// @notice Allows the Governance to approve the particular application
    ///         before individual stake authorizers are able to authorize it.
    function approveApplication(address application) external;

    /// @notice Increases the authorization of the given operator for the given
    ///         application by the given amount. Can only be called by the given
    ///         operator’s authorizer.
    /// @dev Calls `authorizationIncreased(address operator, uint256 amount)`
    ///      on the given application to notify the application about
    ///      authorization change. See `IApplication`.
    function increaseAuthorization(
        address operator,
        address application,
        uint96 amount
    ) external;

    /// @notice Requests decrease of the authorization for the given operator on
    ///         the given application by the provided amount.
    ///         It may not change the authorized amount immediatelly. When
    ///         it happens depends on the application. Can only be called by the
    ///         given operator’s authorizer. Overwrites pending authorization
    ///         decrease for the given operator and application.
    /// @dev Calls `authorizationDecreaseRequested(address operator, uint256 amount)`
    ///      on the given application. See `IApplication`.
    function requestAuthorizationDecrease(
        address operator,
        address application,
        uint96 amount
    ) external;

    /// @notice Requests decrease of all authorizations for the given operator on
    ///         the applications by all authorized amount.
    ///         It may not change the authorized amount immediatelly. When
    ///         it happens depends on the application. Can only be called by the
    ///         given operator’s authorizer. Overwrites pending authorization
    ///         decrease for the given operator and application.
    /// @dev Calls `authorizationDecreaseRequested(address operator, uint256 amount)`
    ///      for each authorized application. See `IApplication`.
    function requestAuthorizationDecrease(address operator) external;

    /// @notice Called by the application at its discretion to approve the
    ///         previously requested authorization decrease request. Can only be
    ///         called by the application that was previously requested to
    ///         decrease the authorization for that operator.
    ///         Returns resulting authorized amount for the application.
    function approveAuthorizationDecrease(address operator)
        external
        returns (uint96);

    /// @notice Decreases the authorization for the given `operator` on
    ///         the given disabled `application`, for all authorized amount.
    ///         Can be called by anyone.
    function forceDecreaseAuthorization(address operator, address application)
        external;

    /// @notice Pauses the given application’s eligibility to slash stakes.
    ///         Besides that stakers can't change authorization to the application.
    ///         Can be called only by the Panic Button of the particular
    ///         application. The paused application can not slash stakes until
    ///         it is approved again by the Governance using `approveApplication`
    ///         function. Should be used only in case of an emergency.
    function pauseApplication(address application) external;

    /// @notice Disables the given application. The disabled application can't
    ///         slash stakers. Also stakers can't increase authorization to that
    ///         application but can decrease without waiting by calling
    ///         `requestAuthorizationDecrease` at any moment. Can be called only
    ///         by the governance. The disabled application can't be approved
    ///         again. Should be used only in case of an emergency.
    function disableApplication(address application) external;

    /// @notice Sets the Panic Button role for the given application to the
    ///         provided address. Can only be called by the Governance. If the
    ///         Panic Button for the given application should be disabled, the
    ///         role address should be set to 0x0 address.
    function setPanicButton(address application, address panicButton) external;

    /// @notice Sets the maximum number of applications one operator can
    ///         authorize. Used to protect against DoSing slashing queue.
    ///         Can only be called by the Governance.
    function setAuthorizationCeiling(uint256 ceiling) external;

    //
    //
    // Stake top-up
    //
    //

    /// @notice Increases the amount of the stake for the given operator.
    ///         Can be called only by the owner or operator.
    /// @dev The sender of this transaction needs to have the amount approved to
    ///      transfer to the staking contract.
    function topUp(address operator, uint96 amount) external;

    /// @notice Propagates information about stake top-up from the legacy KEEP
    ///         staking contract to T staking contract. Can be called only by
    ///         the owner or operator.
    function topUpKeep(address operator) external;

    /// @notice Propagates information about stake top-up from the legacy NU
    ///         staking contract to T staking contract. Can be called only by
    ///         the owner or operator.
    function topUpNu(address operator) external;

    //
    //
    // Undelegating a stake (unstaking)
    //
    //

    /// @notice Reduces the liquid T stake amount by the provided amount and
    ///         withdraws T to the owner. Reverts if there is at least one
    ///         authorization higher than the sum of the legacy stake and
    ///         remaining liquid T stake or if the unstake amount is higher than
    ///         the liquid T stake amount. Can be called only by the owner or
    ///         operator.
    function unstakeT(address operator, uint96 amount) external;

    /// @notice Sets the legacy KEEP staking contract active stake amount cached
    ///         in T staking contract to 0. Reverts if the amount of liquid T
    ///         staked in T staking contract is lower than the highest
    ///         application authorization. This function allows to unstake from
    ///         KEEP staking contract and still being able to operate in T
    ///         network and earning rewards based on the liquid T staked. Can be
    ///         called only by the delegation owner and operator.
    function unstakeKeep(address operator) external;

    /// @notice Reduces cached legacy NU stake amount by the provided amount.
    ///         Reverts if there is at least one authorization higher than the
    ///         sum of remaining legacy NU stake and liquid T stake for that
    ///         operator or if the untaked amount is higher than the cached
    ///         legacy stake amount. If succeeded, the legacy NU stake can be
    ///         partially or fully undelegated on the legacy staking contract.
    ///         This function allows to unstake from NU staking contract and
    ///         still being able to operate in T network and earning rewards
    ///         based on the liquid T staked. Can be called only by the
    ///         delegation owner and operator.
    function unstakeNu(address operator, uint96 amount) external;

    /// @notice Sets cached legacy stake amount to 0, sets the liquid T stake
    ///         amount to 0 and withdraws all liquid T from the stake to the
    ///         owner. Reverts if there is at least one non-zero authorization.
    ///         Can be called only by the delegation owner and operator.
    function unstakeAll(address operator) external;

    //
    //
    // Keeping information in sync
    //
    //

    /// @notice Notifies about the discrepancy between legacy KEEP active stake
    ///         and the amount cached in T staking contract. Slashes the operator
    ///         in case the amount cached is higher than the actual active stake
    ///         amount in KEEP staking contract. Needs to update authorizations
    ///         of all affected applications and execute an involuntary
    ///         allocation decrease on all affected applications. Can be called
    ///         by anyone, notifier receives a reward.
    function notifyKeepStakeDiscrepancy(address operator) external;

    /// @notice Notifies about the discrepancy between legacy NU active stake
    ///         and the amount cached in T staking contract. Slashes the
    ///         operator in case the amount cached is higher than the actual
    ///         active stake amount in NU staking contract. Needs to update
    ///         authorizations of all affected applications and execute an
    ///         involuntary allocation decrease on all affected applications.
    ///         Can be called by anyone, notifier receives a reward.
    function notifyNuStakeDiscrepancy(address operator) external;

    /// @notice Sets the penalty amount for stake discrepancy and reward
    ///         multiplier for reporting it. The penalty is seized from the
    ///         operator account, and 5% of the penalty, scaled by the
    ///         multiplier, is given to the notifier. The rest of the tokens are
    ///         burned. Can only be called by the Governance. See `seize` function.
    function setStakeDiscrepancyPenalty(
        uint96 penalty,
        uint256 rewardMultiplier
    ) external;

    /// @notice Sets reward in T tokens for notification of misbehaviour
    ///         of one operator. Can only be called by the governance.
    function setNotificationReward(uint96 reward) external;

    /// @notice Transfer some amount of T tokens as reward for notifications
    ///         of misbehaviour
    function pushNotificationReward(uint96 reward) external;

    /// @notice Withdraw some amount of T tokens from notifiers treasury.
    ///         Can only be called by the governance.
    function withdrawNotificationReward(address recipient, uint96 amount)
        external;

    /// @notice Adds operators to the slashing queue along with the amount that
    ///         should be slashed from each one of them. Can only be called by
    ///         application authorized for all operators in the array.
    function slash(uint96 amount, address[] memory operators) external;

    /// @notice Adds operators to the slashing queue along with the amount.
    ///         The notifier will receive reward per each operator from
    ///         notifiers treasury. Can only be called by application
    ///         authorized for all operators in the array.
    function seize(
        uint96 amount,
        uint256 rewardMultipier,
        address notifier,
        address[] memory operators
    ) external;

    /// @notice Takes the given number of queued slashing operations and
    ///         processes them. Receives 5% of the slashed amount.
    ///         Executes `involuntaryAllocationDecrease` function on each
    ///         affected application.
    function processSlashing(uint256 count) external;

    //
    //
    // Auxiliary functions
    //
    //

    /// @notice Returns the authorized stake amount of the operator for the
    ///         application.
    function authorizedStake(address operator, address application)
        external
        view
        returns (uint96);

    /// @notice Returns staked amount of T, Keep and Nu for the specified
    ///         operator.
    /// @dev    All values are in T denomination
    function stakes(address operator)
        external
        view
        returns (
            uint96 tStake,
            uint96 keepInTStake,
            uint96 nuInTStake
        );

    /// @notice Returns start staking timestamp for T stake.
    /// @dev    This value is set at most once, and only when a stake is created
    ///         with T tokens. If a stake is created from a legacy stake,
    ///         this value will remain as zero
    function getStartTStakingTimestamp(address operator)
        external
        view
        returns (uint256);

    /// @notice Returns staked amount of NU for the specified operator
    function stakedNu(address operator) external view returns (uint256);

    /// @notice Gets the stake owner, the beneficiary and the authorizer
    ///         for the specified operator address.
    /// @return owner Stake owner address.
    /// @return beneficiary Beneficiary address.
    /// @return authorizer Authorizer address.
    function rolesOf(address operator)
        external
        view
        returns (
            address owner,
            address payable beneficiary,
            address authorizer
        );

    /// @notice Returns length of application array
    function getApplicationsLength() external view returns (uint256);

    /// @notice Returns length of slashing queue
    function getSlashingQueueLength() external view returns (uint256);

    /// @notice Returns minimum possible stake for T, KEEP or NU in T denomination
    /// @dev    For example, if the given operator has 10 T, 20 KEEP, and
    ///         30 NU staked, their max authorization is 40, then `getMinStaked`
    ///         for that operator returns 0 for KEEP stake type, 10 for NU stake
    ///         type, and 0 for T stake type. In other words, minimum staked
    ///         amount for the given stake type is the minimum amount of stake
    ///         of the given type that needs to be preserved in the contract to
    ///         satisfy the maximum application authorization given the amounts
    ///         of other stake types for that operator.
    function getMinStaked(address operator, StakeType stakeTypes)
        external
        view
        returns (uint96);

    /// @notice Returns available amount to authorize for the specified application
    function getAvailableToAuthorize(address operator, address application)
        external
        view
        returns (uint96);
}
