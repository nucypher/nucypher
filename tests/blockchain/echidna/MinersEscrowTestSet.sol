pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "./MasterContract.sol";
import "./Fixtures.sol";


/**
* @notice Prepares one active miner which can mine in current period
**/
contract MinersEscrow1 is DefaultMinersEscrow {

    constructor(NuCypherToken _token, address _miner) public DefaultMinersEscrow(_token) {
        miners.push(_miner);
        MinerInfo storage info = minerInfo[_miner];
        info.value = 1000;
        info.confirmedPeriod1 = getCurrentPeriod() - 1;
        info.confirmedPeriod2 = getCurrentPeriod();
        info.stakes.push(StakeInfo(getCurrentPeriod() - 1, 0, 100, info.value));

        lockedPerPeriod[info.confirmedPeriod1] = info.value;
        lockedPerPeriod[info.confirmedPeriod2] = info.value;
    }

}


/**
* @notice Tests that specified miner can only mine and get reward and can't withdraw
**/
contract MinersEscrowTest1 is MinersEscrowABI {

    address miner = address(this);

    constructor() public {
        NuCypherToken token = Fixtures.createDefaultToken();
        MinersEscrow escrow = new MinersEscrow1(token, miner);
        build(token, escrow, 0x0);
        token.transfer(address(escrow), 1000);
    }

    function echidnaMiningRewardTest() public view returns (bool) {
        (uint256 value,,,) = escrow.minerInfo(miner);
        return value >= 1000 && value <= 1001;
    }

}


/**
* @notice Prepares one miner that were active in a past and have partially unlocked tokens
**/
contract MinersEscrow2 is MinersEscrow1 {

    constructor(NuCypherToken _token, address _miner) public MinersEscrow1(_token, _miner) {
        MinerInfo storage info = minerInfo[_miner];
        info.stakes[0].lockedValue = 900;
        lockedPerPeriod[info.confirmedPeriod1] = 0;
        info.confirmedPeriod1 = EMPTY_CONFIRMED_PERIOD;
    }

}


/**
* @notice Tests that specified miner can only withdraw unlocked tokens
**/
contract MinersEscrowTest2 is MinersEscrowABI {

    address miner = address(this);

    constructor() public {
        NuCypherToken token = Fixtures.createDefaultToken();
        MinersEscrow escrow = new MinersEscrow2(token, miner);
        build(token, escrow, 0x0);
        token.transfer(address(escrow), 1000);
    }

    function echidnaLockedTokensTest() public view returns (bool) {
        (uint256 value,,,) = escrow.minerInfo(miner);
        return value >= 900 && value <= 1000;
    }

}
