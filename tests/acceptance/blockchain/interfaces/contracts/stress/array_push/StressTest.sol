pragma solidity ^0.6.1;


contract StressTest {
    uint256[] history;

    function append(uint256 value) external returns (uint256) {
        history[history.length] = value;
        return value;
    }

//    function history() external {
//        return history;
//    }
}

