pragma solidity ^0.4.8;
import "./Token.sol";

contract Escrow {
    /*
       This contract holds money and is being controlled by the Jury contract
       This contract is a personal "multisig wallet" for each Ursula to use.
       If someone else deposits to this wallet, this will be considered a donation
       to Ursula :-P
    */

    address creator;
    address mint;
    address jury;

    uint256 locked = 0;

    function Escrow(address _mint, address _jury) {
        creator = msg.sender;
        mint = _mint;
        jury = _jury;
    }

    function setLock(uint256 _value) returns (bool success) {
        if (msg.sender == jury) {
            locked = _value;
            return true;}
        else
            return false;
    }

    function withdraw(uint256 _value) returns (bool success) {
        if (msg.sender != creator)
            return false;

        Token instance = Token(mint);

        if (_value <= instance.balanceOf(address(this)) - locked) {
            return instance.transfer(creator, _value);}
        else
            return false;
    }
}
