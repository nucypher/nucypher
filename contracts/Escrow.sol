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

    function Escrow(address _mint, address _jury) {
        creator = msg.sender;
        mint = _mint;
        jury = _jury;
    }

    function withdraw(uint256 _value) returns (bool success) {
        if (msg.sender != jury) return false;
        Token instance = Token(mint);
        return instance.transfer(creator, _value);
    }
}
