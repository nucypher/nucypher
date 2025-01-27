import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/interfaces/IERC1271.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract SmartContractWallet is IERC1271, Ownable {
    using ECDSA for bytes32;

    uint public balance;

    bytes4 internal constant MAGICVALUE = 0x1626ba7e;
    bytes4 constant internal INVALID_SIGNATURE = 0xffffffff;

    constructor(address _owner) Ownable(_owner) public {}

    function deposit() external payable {
        balance += msg.value;
    }

    function withdraw(uint amount) external onlyOwner {
        require(amount <= balance, "Amount exceeds balance");
        balance -= amount;
        payable(owner()).transfer(amount);
    }

    function isValidSignature(bytes32 _hash, bytes memory _signature) public view override returns (bytes4) {
        address signer = _hash.recover(_signature);
        if (signer == owner()) {
            return MAGICVALUE;
        } else {
            return INVALID_SIGNATURE;
        }
    }
}
