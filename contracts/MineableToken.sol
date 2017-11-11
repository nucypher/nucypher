pragma solidity ^0.4.11;


import "zeppelin-solidity/contracts/token/StandardToken.sol";
import "zeppelin-solidity/contracts/ownership/Ownable.sol";


/**
 * @title Mintable token
 * @dev Based on code by zeppelin-solidity/contracts/token/MintableToken.sol
 */
contract MineableToken is StandardToken, Ownable {
    event Mint(address indexed to, uint256 amount);
    event MintFinished();

    bool public mintingFinished = false;
    mapping (address => bool) public isMiner;
    uint256 public futureSupply;

    /**
    * @dev Check whether can mining
    **/
    modifier canMint() {
        require(!mintingFinished && isMiner[msg.sender]);
        _;
    }

    /**
    * @notice Function to add rights for mining.
    * @param miner Address of miner
    */
    function addMiner(address miner) onlyOwner public {
        isMiner[miner] = true;
    }

    /**
    * @notice Function to remove rights for mining.
    * @param miner Address of miner
    */
    function removeMiner(address miner) onlyOwner public {
        isMiner[miner] = false;
    }

    /**
    * @notice Function to mint tokens
    * @param _to The address that will receive the minted tokens.
    * @param _amount The amount of tokens to mint.
    * @return A boolean that indicates if the operation was successful.
    */
    function mint(address _to, uint256 _amount) canMint public returns (bool) {
        require(totalSupply + _amount <= futureSupply);
        totalSupply = totalSupply.add(_amount);
        balances[_to] = balances[_to].add(_amount);
        Mint(_to, _amount);
        Transfer(0x0, _to, _amount);
        return true;
    }

    /**
    * @notice Function to stop minting new tokens.
    * @return True if the operation was successful.
    */
    function finishMinting() onlyOwner public returns (bool) {
        mintingFinished = true;
        MintFinished();
        return true;
    }

}
