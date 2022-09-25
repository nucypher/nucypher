// contracts/MyNFT.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "zeppelin/token/ERC721/ERC721.sol";

contract ConditionNFT is ERC721 {
    constructor() ERC721("ConditionsNFT", "cNFT") {
    }

    /**
    * @dev Mints a new NFT.
    * @param _to The address that will own the minted NFT.
    * @param _tokenId of the NFT to be minted by the msg.sender.
    */
    function mint(address _to, uint256 _tokenId) external {
        super._mint(_to, _tokenId);
    }
}
