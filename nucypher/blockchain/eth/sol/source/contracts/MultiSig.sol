pragma solidity ^0.5.3;


import "zeppelin/math/SafeMath.sol";


/**
* @notice Multi-signature contract with off-chain signing
**/
contract MultiSig {
    using SafeMath for uint256;

    event Executed(address indexed sender, uint256 indexed nonce, address indexed destination, uint256 value);
    event OwnerAdded(address indexed owner);
    event OwnerRemoved(address indexed owner);
    event RequirementChanged(uint16 required);

    uint256 constant public MAX_OWNER_COUNT = 50;

    uint256 public nonce;
    uint8 public required;
    mapping (address => bool) public isOwner;
    address[] public owners;

    // @notice Only this contract can call method
    modifier onlyThisContract() {
        require(msg.sender == address(this));
        _;
    }

    function () external payable {}

    /**
    * @param _required Number of required signings
    * @param _owners List of initial owners.
    **/
    constructor (uint8 _required, address[] memory _owners) public {
        require(_owners.length <= MAX_OWNER_COUNT &&
            _required <= _owners.length &&
            _required > 0);

        for (uint256 i = 0; i < _owners.length; i++) {
            address owner = _owners[i];
            require(!isOwner[owner] && owner != address(0));
            isOwner[owner] = true;
        }
        owners = _owners;
        required = _required;
    }

    /**
    * @notice Get unsigned hash for transaction parameters
    * @dev Follows ERC191 signature scheme: https://github.com/ethereum/EIPs/issues/191
    * @param _sender Trustee who will execute the transaction
    * @param _destination Destination address
    * @param _value Amount of ETH to transfer
    * @param _data Call data
    * @param _nonce Nonce
    **/
    function getUnsignedTransactionHash(
        address _sender,
        address _destination,
        uint256 _value,
        bytes memory _data,
        uint256 _nonce
    )
        public view returns (bytes32)
    {
        return keccak256(
            abi.encodePacked(byte(0x19), byte(0), address(this), _sender, _destination, _value, _data, _nonce));
    }

    /**
    * @dev Note that address recovered from signatures must be strictly increasing
    * @param _sigV Array of signatures values V
    * @param _sigR Array of signatures values R
    * @param _sigS Array of signatures values S
    * @param _destination Destination address
    * @param _value Amount of ETH to transfer
    * @param _data Call data
    **/
    function execute(
        uint8[] calldata _sigV,
        bytes32[] calldata _sigR,
        bytes32[] calldata _sigS,
        address _destination,
        uint256 _value,
        bytes calldata _data
    )
        external
    {
        require(_sigR.length >= required &&
            _sigR.length == _sigS.length &&
            _sigR.length == _sigV.length);

        bytes32 txHash = getUnsignedTransactionHash(msg.sender, _destination, _value, _data, nonce);
        address lastAdd = address(0);
        for (uint256 i = 0; i < _sigR.length; i++) {
            address recovered = ecrecover(txHash, _sigV[i], _sigR[i], _sigS[i]);
            require(recovered > lastAdd && isOwner[recovered]);
            lastAdd = recovered;
        }

        emit Executed(msg.sender, nonce, _destination, _value);
        nonce = nonce.add(1);
        (bool callSuccess,) = _destination.call.value(_value)(_data);
        require(callSuccess);
    }

    /**
    * @notice Allows to add a new owner
    * @dev Transaction has to be sent by `execute` method.
    * @param _owner Address of new owner
    **/
    function addOwner(address _owner)
        public
        onlyThisContract
    {
        require(owners.length < MAX_OWNER_COUNT &&
            _owner != address(0) &&
            !isOwner[_owner]);
        isOwner[_owner] = true;
        owners.push(_owner);
        emit OwnerAdded(_owner);
    }

    /**
    * @notice Allows to remove an owner
    * @dev Transaction has to be sent by `execute` method.
    * @param _owner Address of owner
    **/
    function removeOwner(address _owner)
        public
        onlyThisContract
    {
        require(owners.length > required && isOwner[_owner]);
        isOwner[_owner] = false;
        for (uint256 i = 0; i < owners.length - 1; i++) {
            if (owners[i] == _owner) {
                owners[i] = owners[owners.length - 1];
                break;
            }
        }
        owners.length -= 1;
        emit OwnerRemoved(_owner);
    }

    /**
    * @notice Allows to change the number of required signings
    * @dev Transaction has to be sent by `execute` method
    * @param _required Number of required signings
    **/
    function changeRequirement(uint8 _required)
        public
        onlyThisContract
    {
        require(_required <= owners.length && _required > 0);
        required = _required;
        emit RequirementChanged(_required);
    }

}
