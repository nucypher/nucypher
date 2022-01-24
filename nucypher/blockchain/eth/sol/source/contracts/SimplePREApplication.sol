// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "threshold/IStaking.sol";


/**
* @title PRE Application
* @notice Contract handles PRE configuration
*/
contract SimplePREApplication {

    /**
    * @notice Signals that a worker was bonded to the staking provider
    * @param stakingProvider Staking provider address
    * @param worker Worker address
    * @param startTimestamp Timestamp bonding occurred
    */
    event WorkerBonded(address indexed stakingProvider, address indexed worker, uint256 startTimestamp);

    /**
    * @notice Signals that a worker address is confirmed
    * @param stakingProvider Staking provider address
    * @param worker Worker address
    */
    event WorkerConfirmed(address indexed stakingProvider, address indexed worker);

    struct StakingProviderInfo {
        address worker;
        bool workerConfirmed;
        uint256 workerStartTimestamp;
    }

    uint256 public immutable minAuthorization;
    uint256 public immutable minWorkerSeconds;

    IStaking public immutable tStaking;

    mapping (address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) internal _stakingProviderFromWorker;


    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _tStaking T token staking contract
    * @param _minAuthorization Amount of minimum allowable authorization
    * @param _minWorkerSeconds Min amount of seconds while a worker can't be changed
    */
    constructor(
        IStaking _tStaking,
        uint256 _minAuthorization,
        uint256 _minWorkerSeconds
    ) {
        require(
            _tStaking.authorizedStake(address(this), address(this)) == 0,
            "Wrong input parameters"
        );
        minAuthorization = _minAuthorization;
        tStaking = _tStaking;
        minWorkerSeconds = _minWorkerSeconds;
    }

    /**
    * @dev Checks caller is a staking provider or stake owner
    */
    modifier onlyOwnerOrStakingProvider(address _stakingProvider)
    {
        require(isAuthorized(_stakingProvider), "Not owner or provider");
        if (_stakingProvider != msg.sender) {
            (address owner,,) = tStaking.rolesOf(_stakingProvider);
            require(owner == msg.sender, "Not owner or provider");
        }
        _;
    }


    //-------------------------Main-------------------------
    /**
    * @notice Returns staking provider for specified worker
    */
    function stakingProviderFromWorker(address _worker) public view returns (address) {
        return _stakingProviderFromWorker[_worker];
    }

    /**
    * @notice Returns worker for specified staking provider
    */
    function getWorkerFromStakingProvider(address _stakingProvider) public view returns (address) {
        return stakingProviderInfo[_stakingProvider].worker;
    }

    /**
    * @notice Get all tokens delegated to the staking provider
    */
    function authorizedStake(address _stakingProvider) public view returns (uint96) {
        (uint96 tStake, uint96 keepInTStake, uint96 nuInTStake) = tStaking.stakes(_stakingProvider);
        return tStake + keepInTStake + nuInTStake;
    }

    /**
    * @notice Get the value of authorized tokens for active providers as well as providers and their authorized tokens
    * @param _startIndex Start index for looking in providers array
    * @param _maxStakingProviders Max providers for looking, if set 0 then all will be used
    * @return allAuthorizedTokens Sum of authorized tokens for active providers
    * @return activeStakingProviders Array of providers and their authorized tokens.
    * Providers addresses stored as uint256
    * @dev Note that activeStakingProviders[0] is an array of uint256, but you want addresses.
    * Careful when used directly!
    */
    function getActiveStakingProviders(uint256 _startIndex, uint256 _maxStakingProviders)
        external view returns (uint256 allAuthorizedTokens, uint256[2][] memory activeStakingProviders)
    {
        uint256 endIndex = stakingProviders.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxStakingProviders != 0 && _startIndex + _maxStakingProviders < endIndex) {
            endIndex = _startIndex + _maxStakingProviders;
        }
        activeStakingProviders = new uint256[2][](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address stakingProvider = stakingProviders[i];
            StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
            uint256 eligibleAmount = authorizedStake(stakingProvider);
            if (eligibleAmount < minAuthorization || !info.workerConfirmed) {
                continue;
            }
            activeStakingProviders[resultIndex][0] = uint256(uint160(stakingProvider));
            activeStakingProviders[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeStakingProviders, resultIndex)
        }
    }

    /**
    * @notice Returns beneficiary related to the staking provider
    */
    function getBeneficiary(address _stakingProvider) public view returns (address payable beneficiary) {
        (, beneficiary,) = tStaking.rolesOf(_stakingProvider);
    }

    /**
    * @notice Returns true if staking provider has authorized stake to this application
    */
    function isAuthorized(address _stakingProvider) public view returns (bool) {
        return authorizedStake(_stakingProvider) >= minAuthorization;
    }

    /**
    * @notice Returns true if worker has confirmed address
    */
    // TODO maybe _stakingProvider instead of _worker?
    function isWorkerConfirmed(address _worker) public view returns (bool) {
        address stakingProvider = _stakingProviderFromWorker[_worker];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        return info.workerConfirmed;
    }

    /**
    * @notice Return the length of the array of staking providers
    */
    function getStakingProvidersLength() external view returns (uint256) {
        return stakingProviders.length;
    }

    /**
    * @notice Bond worker
    * @param _stakingProvider Staking provider address
    * @param _worker Worker address. Must be a real address, not a contract
    */
    function bondWorker(address _stakingProvider, address _worker)
        external onlyOwnerOrStakingProvider(_stakingProvider)
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(_worker != info.worker, "Specified worker is already bonded with this provider");
        // If this staker had a worker ...
        if (info.worker != address(0)) {
            require(
                block.timestamp >= info.workerStartTimestamp + minWorkerSeconds,
                "Not enough time passed to change worker"
            );
            // Remove the old relation "worker->stakingProvider"
            _stakingProviderFromWorker[info.worker] = address(0);
        }

        if (_worker != address(0)) {
            require(_stakingProviderFromWorker[_worker] == address(0), "Specified worker is already in use");
            require(
                _worker == _stakingProvider || getBeneficiary(_worker) == address(0),
                "Specified worker is a provider"
            );
            // Set new worker->stakingProvider relation
            _stakingProviderFromWorker[_worker] = _stakingProvider;
        }

        if (info.workerStartTimestamp == 0) {
            stakingProviders.push(_stakingProvider);
        }

        // Bond new worker (or unbond if _worker == address(0))
        info.worker = _worker;
        info.workerStartTimestamp = block.timestamp;
        info.workerConfirmed = false;
        emit WorkerBonded(_stakingProvider, _worker, block.timestamp);
    }

    /**
    * @notice Make a confirmation by worker
    */
    function confirmWorkerAddress() external {
        address stakingProvider = _stakingProviderFromWorker[msg.sender];
        require(isAuthorized(stakingProvider), "No stake associated with the worker");
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        require(!info.workerConfirmed, "Worker address is already confirmed");
        require(msg.sender == tx.origin, "Only worker with real address can make a confirmation");
        info.workerConfirmed = true;
        emit WorkerConfirmed(stakingProvider, msg.sender);
    }

}
