import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/interfaces/IERC1271.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract ThresholdSigningMultisig is IERC1271, Ownable {
    using ECDSA for bytes32;

    event Executed(address indexed sender, uint256 indexed nonce, address indexed destination, uint256 value);
    event SignerAdded(address indexed signer);
    event SignerRemoved(address indexed signer);
    event SignerReplaced(address indexed signer, address newSigner);
    event SignedMessageCached(bytes32 indexed hash);
    event ThresholdChanged(uint16 threshold);

    uint256 constant public MAX_SIGNER_COUNT = 30;

    uint256 public nonce;
    mapping (address => bool) public isSigner;
    address[] public signers;
    uint8 public threshold;

    bytes4 internal constant MAGICVALUE = 0x1626ba7e;
    bytes4 constant internal INVALID_SIGNATURE = 0xffffffff;
    mapping(bytes32 => bool) public validSignatures;


    function deposit() external payable {}

    /**
    * @param _threshold Threshold number of required signings
    * @param _signers List of signers.
    **/
    constructor (address[] memory _signers, uint8 _threshold) Ownable(msg.sender) public {
        require(_signers.length <= MAX_SIGNER_COUNT &&
            _threshold <= _signers.length &&
            _threshold > 0);

        for (uint256 i = 0; i < _signers.length; i++) {
            address signer = _signers[i];
            require(!isSigner[signer] && signer != address(0));
            isSigner[signer] = true;
        }
        nonce = 1;
        signers = _signers;
        threshold = _threshold;
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
            abi.encodePacked(address(this), _sender, _destination, _value, _data, _nonce));
    }

    /**
    * @dev Note that address recovered from signatures must be strictly increasing
    * @param _destination Destination address
    * @param _value Amount of ETH to transfer
    * @param _data Call data
    * @param _signature The aggregated signatures for signers
    **/
    function execute(address _destination, uint256 _value, bytes memory _data, bytes memory _signature) external {
        bytes32 _hash = getUnsignedTransactionHash(msg.sender,_destination,_value, _data, nonce);
        require(isValidSignature(_hash, _signature) == MAGICVALUE, "Invalid Signature");
        emit Executed(msg.sender, nonce, _destination, _value);
        nonce++;
        (bool success, ) = _destination.call{value: _value}(_data);
        require(success, "Transaction failed");
    }

    /**
    * @notice Check if the signatures are valid.
    * @param _hash Hash of the transaction
    * @param _signature The signatures for signers
    **/
    function isValidSignature(bytes32 _hash, bytes memory _signature) public view override returns (bytes4) {
        // split up signature bytes into array
        require(_signature.length >= (threshold * 65), "Invalid threshold of signatures");
        if (validSignatures[_hash]) {
            // TODO is this sufficient?
            // - in this case the message hash was previously signed and cached, but
            // what if the _hash is correct but the signature is wrong
            return MAGICVALUE;
        }

        for (uint256 i = 0; i < threshold; i++) {
            (uint8 v, bytes32 r, bytes32 s) = signatureSplit(_signature, i);
            address recovered = ecrecover(_hash, v, r, s);
            if (!isSigner[recovered]) {
                return INVALID_SIGNATURE;
            }
        }

        return MAGICVALUE;
    }

    /**
     * @notice Splits signature bytes into `uint8 v, bytes32 r, bytes32 s`.
     * @dev Make sure to perform a bounds check for @param pos, to avoid out of bounds access on @param signatures
     *      The signature format is a compact form of {bytes32 r}{bytes32 s}{uint8 v}
     *      Compact means uint8 is not padded to 32 bytes.
     * @param pos Which signature to read.
     *            A prior bounds check of this parameter should be performed, to avoid out of bounds access.
     * @param signatures Concatenated {r, s, v} signatures.
     * @return v Recovery ID or Safe signature type.
     * @return r Output value r of the signature.
     * @return s Output value s of the signature.
     */
    function signatureSplit(bytes memory signatures, uint256 pos) internal pure returns (uint8 v, bytes32 r, bytes32 s) {
        /* solhint-disable no-inline-assembly */
        /// @solidity memory-safe-assembly
        assembly {
            let signaturePos := mul(0x41, pos)
            r := mload(add(signatures, add(signaturePos, 0x20)))
            s := mload(add(signatures, add(signaturePos, 0x40)))
            v := byte(0, mload(add(signatures, add(signaturePos, 0x60))))
        }
        /* solhint-enable no-inline-assembly */
    }

    /**
    * @notice Allows to add a new signer
    * @dev Transaction has to be sent by `execute` method.
    * @param _signer Address of new signer
    **/
    function addSigner(address _signer)
        public
        onlyOwner
    {
        require(signers.length < MAX_SIGNER_COUNT, "At max signers");
        require(_signer != address(0) && !isSigner[_signer], "Invalid signer");
        signers.push(_signer);
        isSigner[_signer] = true;
        emit SignerAdded(_signer);
    }

    /**
    * @notice Allows to remove an signer
    * @dev Transaction has to be sent by `execute` method.
    * @param _signer Address of signer
    **/
    function removeSigner(address _signer)
        public
        onlyOwner
    {
        require(signers.length > threshold && isSigner[_signer], "Invalid signer");
        isSigner[_signer] = false;

        uint256 index = signers.length;
        for (uint256 i = 0; i < signers.length; i++) {
            if (signers[i] == _signer) {
                index = i;
                break;
            }
        }
        require(index < signers.length && signers[index] == _signer, "Signer not found");
        signers[index] = signers[signers.length - 1];
        signers.pop(); // Remove last element
        emit SignerRemoved(_signer);
    }

    /**
    * @notice Allows to replace an signer with a new signer.
    * @dev Transaction has to be sent by `execute` method.
    * @param oldSigner Address of signer to be replaced.
    * @param newSigner Address of new signer.
    */
    function replaceSigner(address oldSigner, address newSigner)
        public
        onlyOwner
    {
        require(isSigner[oldSigner] && !isSigner[newSigner], "Invalid Signer");

        removeSigner(oldSigner);
        addSigner(newSigner);
        emit SignerReplaced(oldSigner, newSigner);
    }


    function getSigners() public view returns (address[] memory) {
        return signers;
    }

    /**
    * @notice Allows to change the threshold number of signatures
    * @dev Transaction has to be sent by `execute` method
    * @param _threshold Threshold number of required signatures
    **/
    function changeThreshold(uint8 _threshold)
        public
        onlyOwner
    {
        require(_threshold <= signers.length && _threshold > 0);
        threshold = _threshold;
        emit ThresholdChanged(_threshold);
    }

    function saveSignature(bytes32 _hash, bytes memory _signature) public {
        // Save signature
        require(isValidSignature(_hash, _signature) == MAGICVALUE, "Invalid Signature");

        // TODO: is this sufficient?
        validSignatures[_hash] = true;
        emit SignedMessageCached(_hash);
    }

}
