// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "threshold/IStaking.sol";


/**
* @title PRE Application
* @notice Contract handles PRE configuration
*/
contract SimplePREApplication {

    /**
    * @notice Signals that a worker was bonded to the operator
    * @param operator Operator address
    * @param worker Worker address
    * @param startTimestamp Timestamp bonding occurred
    */
    event WorkerBonded(address indexed operator, address indexed worker, uint256 startTimestamp);

    /**
    * @notice Signals that a worker address is confirmed
    * @param operator Operator address
    * @param worker Worker address
    */
    event WorkerConfirmed(address indexed operator, address indexed worker);

    struct OperatorInfo {
        address worker;
        bool workerConfirmed;
        uint256 workerStartTimestamp;
    }

    uint256 public immutable minAuthorization;
    uint256 public immutable minWorkerSeconds;

    IStaking public immutable tStaking;

    mapping (address => OperatorInfo) public operatorInfo;
    address[] public operators;
    mapping(address => address) internal _operatorFromWorker;


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
    * @dev Checks the existence of an operator in the contract
    */
    modifier onlyOperator()
    {
        require(isAuthorized(msg.sender), "Caller is not the operator");
        _;
    }


    //-------------------------Main-------------------------
    /**
    * @notice Returns operator for specified worker
    */
    function operatorFromWorker(address _worker) public view returns (address) {
        return _operatorFromWorker[_worker];
    }

    /**
    * @notice Returns worker for specified operator
    */
    function getWorkerFromOperator(address _operator) public view returns (address) {
        return operatorInfo[_operator].worker;
    }

    /**
    * @notice Get all tokens delegated to the operator
    */
    function authorizedStake(address _operator) public view returns (uint96) {
        (uint96 tStake, uint96 keepInTStake, uint96 nuInTStake) = tStaking.stakes(_operator);
        return tStake + keepInTStake + nuInTStake;
    }

    /**
    * @notice Get the value of authorized tokens for active operators as well as operators and their authorized tokens
    * @param _startIndex Start index for looking in operators array
    * @param _maxOperators Max operators for looking, if set 0 then all will be used
    * @return allAuthorizedTokens Sum of authorized tokens for active operators
    * @return activeOperators Array of operators and their authorized tokens. Operators addresses stored as uint256
    * @dev Note that activeOperators[0] in an array of uint256, but you want addresses. Careful when used directly!
    */
    function getActiveOperators(uint256 _startIndex, uint256 _maxOperators)
        external view returns (uint256 allAuthorizedTokens, uint256[2][] memory activeOperators)
    {
        uint256 endIndex = operators.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxOperators != 0 && _startIndex + _maxOperators < endIndex) {
            endIndex = _startIndex + _maxOperators;
        }
        activeOperators = new uint256[2][](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address operator = operators[i];
            OperatorInfo storage info = operatorInfo[operator];
            uint256 eligibleAmount = authorizedStake(operator);
            if (eligibleAmount < minAuthorization || !info.workerConfirmed) {
                continue;
            }
            activeOperators[resultIndex][0] = uint256(uint160(operator));
            activeOperators[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeOperators, resultIndex)
        }
    }

    /**
    * @notice Returns beneficiary related to the operator
    */
    function getBeneficiary(address _operator) public view returns (address payable beneficiary) {
        (, beneficiary,) = tStaking.rolesOf(_operator);
    }

    /**
    * @notice Returns true if operator has authorized stake to this application
    */
    function isAuthorized(address _operator) public view returns (bool) {
        return authorizedStake(_operator) >= minAuthorization;
    }

    /**
    * @notice Returns true if worker has confirmed address
    */
    // TODO maybe _operator instead of _worker?
    function isWorkerConfirmed(address _worker) public view returns (bool) {
        address operator = _operatorFromWorker[_worker];
        OperatorInfo storage info = operatorInfo[operator];
        return info.workerConfirmed;
    }

    /**
    * @notice Return the length of the array of operators
    */
    function getOperatorsLength() external view returns (uint256) {
        return operators.length;
    }

    /**
    * @notice Bond worker
    * @param _worker Worker address. Must be a real address, not a contract
    */
    function bondWorker(address _worker) external onlyOperator {
        OperatorInfo storage info = operatorInfo[msg.sender];
        require(_worker != info.worker, "Specified worker is already bonded with this operator");
        // If this staker had a worker ...
        if (info.worker != address(0)) {
            require(
                block.timestamp >= info.workerStartTimestamp + minWorkerSeconds,
                "Not enough time passed to change worker"
            );
            // Remove the old relation "worker->operator"
            _operatorFromWorker[info.worker] = address(0);
        }

        if (_worker != address(0)) {
            require(_operatorFromWorker[_worker] == address(0), "Specified worker is already in use");
            require(
                _worker == msg.sender || getBeneficiary(_worker) == address(0),
                "Specified worker is an operator"
            );
            // Set new worker->operator relation
            _operatorFromWorker[_worker] = msg.sender;
        }

        if (info.workerStartTimestamp == 0) {
            operators.push(msg.sender);
        }

        // Bond new worker (or unbond if _worker == address(0))
        info.worker = _worker;
        info.workerStartTimestamp = block.timestamp;
        info.workerConfirmed = false;
        emit WorkerBonded(msg.sender, _worker, block.timestamp);
    }

    /**
    * @notice Make a confirmation by worker
    */
    function confirmWorkerAddress() external {
        address operator = _operatorFromWorker[msg.sender];
        require(isAuthorized(operator), "No stake associated with the worker");
        OperatorInfo storage info = operatorInfo[operator];
        require(!info.workerConfirmed, "Worker address is already confirmed");
        require(msg.sender == tx.origin, " Only worker with real address can make a confirmation");
        info.workerConfirmed = true;
        emit WorkerConfirmed(operator, msg.sender);
    }

}
