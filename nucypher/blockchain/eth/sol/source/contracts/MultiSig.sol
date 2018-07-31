pragma solidity ^0.4.24;


import "zeppelin/math/SafeMath.sol";


/**
* @notice Multi-signature contract with off-chain signing
**/
contract MultiSig {
    using SafeMath for uint256;

    uint256 public nonce;
    uint16 public threshold;
    mapping (address => bool) public isOwner;
    address[] public owners;

    function () public payable {}

    /**
    * @param _threshold Number of required signings
    * @param _owners List of initial owners.
    **/
    constructor (uint16 _threshold, address[] _owners) public {
        require(_owners.length > 0 &&
        _threshold <= _owners.length &&
        _threshold > 0);

        for (uint256 i = 0; i < _owners.length; i++) {
            address owner = _owners[i];
            require(!isOwner[owner] && owner != 0x0);
            isOwner[owner] = true;
        }
        owners = _owners;
        threshold = _threshold;
    }

    /**
    * @notice Get unsigned hash for transaction parameters
    * @dev Follows ERC191 signature scheme: https://github.com/ethereum/EIPs/issues/191
    * @param _destination Destination address
    * @param _value Amount of ETH to transfer
    * @param _data Call data
    * @param _nonce Nonce
    **/
    function getUnsignedTransactionHash(
        address _destination,
        uint256 _value,
        bytes _data,
        uint256 _nonce
    )
        public view returns (bytes32)
    {
        return keccak256(
            abi.encodePacked(byte(0x19), byte(0), address(this), _destination, _value, _data, _nonce));
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
        uint8[] _sigV,
        bytes32[] _sigR,
        bytes32[] _sigS,
        address _destination,
        uint256 _value,
        bytes _data
    )
        external
    {
        require(_sigR.length == threshold &&
            _sigR.length == _sigS.length &&
            _sigR.length == _sigV.length);

        bytes32 txHash = getUnsignedTransactionHash(_destination, _value, _data, nonce);
        address lastAdd = 0x0;
        for (uint256 i = 0; i < threshold; i++) {
            address recovered = ecrecover(txHash, _sigV[i], _sigR[i], _sigS[i]);
            require(recovered > lastAdd && isOwner[recovered]);
            lastAdd = recovered;
        }

        nonce = nonce.add(1);
        require(_destination.call.value(_value)(_data));
    }

}
