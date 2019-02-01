pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";
import "./Fixtures.sol";
import "./MasterContract.sol";
import "./MinersEscrowTestSet.sol";


/**
* @notice Prepares and tests one node with reward
**/
contract PolicyManagerTest1 is PolicyManager {

    constructor() public PolicyManager(Fixtures.createDefaultMinersEscrow()) {
        nodes[Fixtures.echidnaCaller()] = NodeInfo(1000, 0, getCurrentPeriod() - 1, 0);
    }

    function echidnaRewardTest() public view returns (bool) {
        // TODO this test should fail after withdraw reward
        // but need to transfer ETH somehow to PolicyManager contract in tests preparation
        return nodes[Fixtures.echidnaCaller()].reward == 1000;
    }

}


/**
* @notice Prepares one node with reward  and one policy for that node
**/
contract PolicyManager2 is PolicyManager {

    constructor(MinersEscrow _escrow, address _node) public PolicyManager(_escrow) {
        NodeInfo storage nodeInfo = nodes[_node];
        nodeInfo.reward = 1000;
        nodeInfo.lastMinedPeriod = getCurrentPeriod() - 2;

        Policy storage policy = policies[bytes16(1)];
        policy.client  = Fixtures.addressList(3);
        policy.rewardRate = 100;
        policy.firstPartialReward = 0;
        policy.startPeriod = getCurrentPeriod() - 1;
        policy.lastPeriod = policy.startPeriod + 100;
        policy.arrangements.push(ArrangementInfo(_node, getCurrentPeriod(), 0));

        nodeInfo.rewardDelta[policy.startPeriod] = 100;
        nodeInfo.rewardDelta[policy.lastPeriod + 1] = -100;
    }

    function getCurrentPeriod() public view returns (uint16) {
        return escrow.getCurrentPeriod();
    }

}


/**
* @notice Tests that node can get only reward for available policy
**/
contract PolicyManagerTest2 is MinersEscrowABI, PolicyManagerABI {

    address miner = address(this);

    constructor() public {
        NuCypherToken token = Fixtures.createDefaultToken();
        MinersEscrow escrow = new MinersEscrow1(token, miner);
        PolicyManager policyManager = new PolicyManager2(escrow, miner);
        build(token, escrow, policyManager);
        token.transfer(address(escrow), 1000);
    }

    function echidnaPolicyRewardTest() public view returns (bool) {
        (uint256 reward,,,) = policyManager.nodes(miner);
        return reward <= 1100;
    }

}
