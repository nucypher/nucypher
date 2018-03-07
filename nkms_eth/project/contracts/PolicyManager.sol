pragma solidity ^0.4.18;


import "./zeppelin/token/ERC20/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
import "./zeppelin/math/Math.sol";
import "./MinersEscrow.sol";
import "./NuCypherKMSToken.sol";
import "./proxy/Upgradeable.sol";


/**
* @notice Contract holds policy data and locks fees
**/
contract PolicyManager is Upgradeable {
    using SafeERC20 for NuCypherKMSToken;
    using SafeMath for uint256;

    event PolicyCreated(
        bytes20 indexed policyId,
        address indexed client,
        address indexed node
    );
    event PolicyRevoked(bytes20 indexed policyId);
    event Withdrawn(address indexed node, uint256 value);
    event Refunded(
        bytes20 indexed policyId,
        address indexed client,
        uint256 value
    );

//    enum PolicyState { Pending, Active }
//    enum PolicyType { Periods }

    struct Policy {
        address client;
        address node;
//        PolicyState state;

        // policy for activity periods
        uint256 rate;
        uint256 startPeriod;
        uint256 lastPeriod;
        uint256 indexOfDowntimePeriods;
    }

    struct NodeInfo {
        uint256 reward;
        mapping (uint256 => uint256) rewardByPeriod;
    }

    bytes20 constant RESERVED_POLICY_ID = bytes20(0);
    address constant RESERVED_NODE = 0x0;

    MinersEscrow public escrow;
    mapping (bytes20 => Policy) public policies;
    mapping (address => NodeInfo) public nodes;

    /**
    * @notice Constructor sets address of the escrow contract
    * @param _escrow Escrow contract
    **/
    function PolicyManager(
        MinersEscrow _escrow
    )
        public
    {
        require(address(_escrow) != 0x0);
        escrow = _escrow;
    }

    /**
    * @notice Create policy by client
    * @dev Generate policy id before creation
    * @param _policyId Policy id
    * @param _node Node that will handle policy
    * @param _numberOfPeriods Duration of the policy in periods
    **/
    function createPolicy(
        bytes20 _policyId,
        address _node,
        uint256 _numberOfPeriods
    )
        public payable
    {
        require(
            policies[_policyId].rate == 0 &&
            _node != RESERVED_NODE &&
            _numberOfPeriods != 0 &&
            escrow.getLockedTokens(_node) != 0 &&
            msg.value > 0 &&
            msg.value % _numberOfPeriods == 0 &&
            _policyId != RESERVED_POLICY_ID
        );
        Policy storage policy = policies[_policyId];
        policy.client = msg.sender;
        policy.node = _node;
//        policy.state = PolicyState.Pending;
        uint256 currentPeriod = escrow.getCurrentPeriod();
        policy.startPeriod = currentPeriod.add(1);
        policy.lastPeriod = currentPeriod.add(_numberOfPeriods);
        uint256 feeByPeriod = msg.value.div(_numberOfPeriods);
        policy.rate = feeByPeriod;

        NodeInfo storage node = nodes[_node];
        for (uint256 i = policy.startPeriod; i <= policy.lastPeriod; i++) {
            node.rewardByPeriod[i] = node.rewardByPeriod[i].add(feeByPeriod);
        }
        policy.indexOfDowntimePeriods = escrow.getDowntimePeriodsLength(_node);
        PolicyCreated(_policyId, msg.sender, _node);
    }

//    /**
//    * @notice Confirm policy by node
//    * @param _policyId Policy id
//    **/
//    function confirmPolicy(bytes20 _policyId) public {
//        Policy policy = policies[_policyId];
//        require(policy.state == PolicyState.Pending &&
//            policy.node == msg.sender);
//        policy.state = PolicyState.Active;
//    }

    /**
    * @notice Update node reward
    * @param _node Node address
    * @param _period Processed period
    **/
    function updateReward(address _node, uint256 _period) external {
        require(msg.sender == address(escrow));
        NodeInfo storage node = nodes[_node];
        node.reward = node.reward.add(node.rewardByPeriod[_period]);
        delete node.rewardByPeriod[_period];
    }

    /**
    * @notice Withdraw fee by node
    **/
    function withdraw() public {
        NodeInfo storage node = nodes[msg.sender];
        uint256 reward = node.reward;
        require(reward != 0);
        node.reward = 0;
        msg.sender.transfer(reward);
        Withdrawn(msg.sender, reward);
    }

    /**
    * @notice Revoke policy by client
    * @param _policyId Policy id
    **/
    function revokePolicy(bytes20 _policyId) public {
        Policy storage policy = policies[_policyId];
        require(policy.client == msg.sender);
        uint256 refund = calculateRefund(_policyId);
        NodeInfo storage node = nodes[policy.node];
        for (uint256 i = policy.startPeriod; i <= policy.lastPeriod; i++) {
            node.rewardByPeriod[i] = node.rewardByPeriod[i].sub(policy.rate);
            refund = refund.add(policy.rate);
        }
        delete policies[_policyId];
        if (refund > 0) {
            msg.sender.transfer(refund);
            Refunded(_policyId, msg.sender, refund);
        }
        PolicyRevoked(_policyId);
    }

    /**
    * @notice Refund part of fee by client
    * @param _policyId Policy id
    **/
    function refund(bytes20 _policyId) public {
        Policy storage policy = policies[_policyId];
//        require(policy.state == PolicyState.Active &&
//            msg.sender == policy.client);
        require(msg.sender == policy.client);

        uint256 refundValue = calculateRefund(_policyId);
        address client = policy.client;
        if (policy.startPeriod > policy.lastPeriod) {
            delete policies[_policyId];
        }
        if (refundValue > 0) {
            client.transfer(refundValue);
            Refunded(_policyId, client, refundValue);
        }
    }

    /**
    * @notice Calculate amount of refund
    * @param _policyId Policy id
    **/
    //TODO extract checkRefund method
    function calculateRefund(bytes20 _policyId) internal returns (uint256) {
        Policy storage policy = policies[_policyId];
        uint256 currentPeriod = escrow.getCurrentPeriod();
        uint256 maxPeriod = Math.min256(currentPeriod, policy.lastPeriod);
        uint256 minPeriod = policy.startPeriod;
        uint256 downtimePeriods = 0;
        uint256 length = escrow.getDowntimePeriodsLength(policy.node);
        for (uint256 i = policy.indexOfDowntimePeriods; i < length; i++) {
            uint256 startPeriod;
            uint256 endPeriod;
            (startPeriod, endPeriod) = escrow.getDowntimePeriods(policy.node, i);
            if (startPeriod > maxPeriod) {
                break;
            } else if (endPeriod < minPeriod) {
                continue;
            }
            uint256 max = Math.min256(maxPeriod, endPeriod);
            uint256 min = Math.max256(minPeriod, startPeriod);
            downtimePeriods = downtimePeriods.add(max.sub(min).add(1));
            if (maxPeriod <= endPeriod) {
                break;
            }
        }
        policy.indexOfDowntimePeriods = i;
        uint256 lastActivePeriod = escrow.getLastActivePeriod(policy.node);
        if (i == length && lastActivePeriod < maxPeriod) {
            min = Math.max256(minPeriod.sub(1), lastActivePeriod);
            downtimePeriods = downtimePeriods.add(maxPeriod.sub(min));
        }
        policy.startPeriod = maxPeriod.add(1);

        return policy.rate.mul(downtimePeriods);
    }

    /**
    * @dev Used only in verifyState(address) method
    **/
    function getPolicyField(bytes20 _policyId, uint8 _field)
        public view returns (bytes32)
    {
        Policy storage policy = policies[_policyId];
        if (_field == 0) {
            return bytes32(policy.client);
        } else if (_field == 1) {
            return bytes32(policy.node);
        } else if (_field == 2) {
            return bytes32(policy.rate);
        } else if (_field == 3) {
            return bytes32(policy.startPeriod);
        } else if (_field == 4) {
            return bytes32(policy.lastPeriod);
        } else if (_field == 5) {
            return bytes32(policy.indexOfDowntimePeriods);
        }
    }

    /**
    * @dev Used only in verifyState(address) method
    **/
    function getNodeInfoField(address _node, uint8 _field, uint256 _period)
        public view returns (uint256)
    {
        NodeInfo storage nodeInfo = nodes[_node];
        if (_field == 0) {
            return nodeInfo.reward;
        } else if (_field == 1) {
            return nodeInfo.rewardByPeriod[_period];
        }
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(address(delegateGet(_testTarget, "escrow()")) == address(escrow));
        Policy storage policy = policies[RESERVED_POLICY_ID];
        require(address(delegateGet(_testTarget, "getPolicyField(bytes20,uint8)",
            RESERVED_POLICY_ID, 0)) == policy.client);
        require(address(delegateGet(_testTarget, "getPolicyField(bytes20,uint8)",
            RESERVED_POLICY_ID, 1)) == policy.node);
        require(uint256(delegateGet(_testTarget, "getPolicyField(bytes20,uint8)",
            RESERVED_POLICY_ID, 2)) == policy.rate);
        require(uint256(delegateGet(_testTarget, "getPolicyField(bytes20,uint8)",
            RESERVED_POLICY_ID, 3)) == policy.startPeriod);
        require(uint256(delegateGet(_testTarget, "getPolicyField(bytes20,uint8)",
            RESERVED_POLICY_ID, 4)) == policy.lastPeriod);
        require(uint256(delegateGet(_testTarget, "getPolicyField(bytes20,uint8)",
            RESERVED_POLICY_ID, 5)) == policy.indexOfDowntimePeriods);
        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        require(uint256(delegateGet(_testTarget, "getNodeInfoField(address,uint8,uint256)",
            bytes32(RESERVED_NODE), 0, 0)) == nodeInfo.reward);
        require(uint256(delegateGet(_testTarget, "getNodeInfoField(address,uint8,uint256)",
            bytes32(RESERVED_NODE), 1, 22)) == nodeInfo.rewardByPeriod[22]);
        require(uint256(delegateGet(_testTarget, "getNodeInfoField(address,uint8,uint256)",
            bytes32(RESERVED_NODE), 1, 44)) == nodeInfo.rewardByPeriod[44]);
    }

    function finishUpgrade(address _target) public onlyOwner {
        PolicyManager policyManager = PolicyManager(_target);
        escrow = policyManager.escrow();
        // Create fake Policy and NodeInfo to use them in verifyState(address)
        Policy storage policy = policies[RESERVED_POLICY_ID];
        policy.client = owner;
        policy.node = owner;
        policy.startPeriod = 1;
        policy.lastPeriod = 2;
        policy.rate = 3;
        policy.indexOfDowntimePeriods = 4;
        NodeInfo storage nodeInfo = nodes[RESERVED_NODE];
        nodeInfo.reward = 100;
        nodeInfo.rewardByPeriod[22] = 33;
        nodeInfo.rewardByPeriod[44] = 55;
    }

}
