import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/interfaces/IERC1271.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract ThresholdSigningMultisig is IERC1271, Ownable {
    using ECDSA for bytes32;

    event Executed(address indexed sender, uint256 indexed nonce, address indexed destination, uint256 value);
    event SignerAdded(address indexed signer);
    event SignerRemoved(address indexed signer);
    event SignerReplaced(address indexed signer, address newSigner);
    event ThresholdChanged(uint16 threshold);

    uint256 constant public MAX_SIGNER_COUNT = 30;

    uint256 public nonce;
    mapping (address => bool) public isSigner;
    address[] public signers;
    uint8 public threshold;

    bytes4 internal constant MAGICVALUE = 0x1626ba7e;
    bytes4 constant internal INVALID_SIGNATURE = 0xffffffff;


    // @notice Only this contract can call method
    modifier onlyThisContract() {
        require(msg.sender == address(this));
        _;
    }

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
    * @param _signatures The signatures for signers
    **/
    function execute(address _destination, uint256 _value, bytes memory _data, bytes[] memory _signatures) external {
        bytes32 _hash = getUnsignedTransactionHash(msg.sender,_destination,_value, _data, nonce);
        require(isValidSignatures(_hash, _signatures) == MAGICVALUE, "Invalid Signature");
        emit Executed(msg.sender, nonce, _destination, _value);
        nonce++;
        (bool success, ) = _destination.call{value: _value}(_data);
        require(success, "Transaction failed");
    }

    /**
    * @dev Note that addresses recovered from signatures must be strictly increasing
    * @param _hash Hash of the transaction
    * @param _signatures The signatures for signers
    **/
    function isValidSignatures(bytes32 _hash, bytes[] memory _signatures) public view returns (bytes4) {
        uint256 thresholdCounter = 0;
        address lastAddress = address(0);
        for (uint256 i = 0; i < _signatures.length; i++) {
            address recovered = _hash.recover(_signatures[i]);
            if (recovered <= lastAddress || !isSigner[recovered]) {
                return INVALID_SIGNATURE;
            }
            lastAddress = recovered;
            thresholdCounter++;
            if (thresholdCounter >= threshold) {
                return MAGICVALUE;
            }
        }

        return INVALID_SIGNATURE;
    }

    function isValidSignature(bytes32 _hash, bytes memory _signature) public view override returns (bytes4) {
        // split up signature bytes into array
        require(_signature.length >= (threshold * 65), "Invalid threshold of signatures");
        address lastAddress = address(0);
        for (uint256 i = 0; i < threshold; i++) {
            (uint8 v, bytes32 r, bytes32 s) = signatureSplit(_signature, i);
            address recovered = ecrecover(_hash, v, r, s);
            if (recovered <= lastAddress || !isSigner[recovered]) {
                return INVALID_SIGNATURE;
            }
            lastAddress = recovered;
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
        onlyThisContract
    {
        require(signers.length < MAX_SIGNER_COUNT &&
            _signer != address(0) &&
            !isSigner[_signer]);
        isSigner[_signer] = true;
        signers.push(_signer);
        emit SignerAdded(_signer);
    }

    /**
    * @notice Allows to remove an signer
    * @dev Transaction has to be sent by `execute` method.
    * @param _signer Address of signer
    **/
    function removeSigner(address _signer)
        public
        onlyThisContract
    {
        require(signers.length > threshold && isSigner[_signer]);
        isSigner[_signer] = false;
        for (uint256 i = 0; i < signers.length - 1; i++) {
            if (signers[i] == _signer) {
                signers[i] = signers[signers.length - 1];
                break;
            }
        }
        signers.pop();
        emit SignerRemoved(_signer);
    }

    /**
    * @notice Allows to replace an signer with a new signer.
    * @dev Transaction has to be sent by `execute` method.
    * @param signer Address of signer to be replaced.
    * @param newSigner Address of new signer.
    */
    function replaceSigner(address signer, address newSigner)
        public
        onlyThisContract
    {
        require(isSigner[signer] && !isSigner[newSigner]);
        for (uint256 i=0; i < signers.length; i++) {
            if (signers[i] == signer) {
                signers[i] = newSigner;
                break;
            }
        }
        isSigner[signer] = false;
        isSigner[newSigner] = true;
        emit SignerReplaced(signer, newSigner);
    }

    /**
    * @notice Allows to change the threshold number of signatures
    * @dev Transaction has to be sent by `execute` method
    * @param _threshold Threshold number of required signatures
    **/
    function changeThreshold(uint8 _threshold)
        public
        onlyThisContract
    {
        require(_threshold <= signers.length && _threshold > 0);
        threshold = _threshold;
        emit ThresholdChanged(_threshold);
    }

}
