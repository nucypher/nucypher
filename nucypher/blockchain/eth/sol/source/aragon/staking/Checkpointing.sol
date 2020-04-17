pragma solidity ^0.6.5;


library Checkpointing {
    uint256 private constant MAX_UINT192 = uint256(uint192(-1));
    uint256 private constant MAX_UINT64 = uint256(uint64(-1));

    string private constant ERROR_PAST_CHECKPOINT = "CHECKPOINT_PAST_CHECKPOINT";
    string private constant ERROR_TIME_TOO_BIG = "CHECKPOINT_TIME_TOO_BIG";
    string private constant ERROR_VALUE_TOO_BIG = "CHECKPOINT_VALUE_TOO_BIG";

    struct Checkpoint {
        uint64 time;
        uint192 value;
    }

    function add(Checkpoint[] storage self, uint256 time, uint256 value) internal {
        require(time <= MAX_UINT64, ERROR_TIME_TOO_BIG);
        require(value <= MAX_UINT192, ERROR_VALUE_TOO_BIG);

        add192(self, uint64(time), uint192(value));
    }

    function add64(Checkpoint[] storage self, uint64 time, uint256 value) internal {
        require(value <= MAX_UINT192, ERROR_VALUE_TOO_BIG);

        add192(self, time, uint192(value));
    }

    function get(Checkpoint[] storage self, uint256 time) internal view returns (uint256) {
        require(time <= MAX_UINT64, ERROR_TIME_TOO_BIG);

        return uint256(get192(self, uint64(time)));
    }

    function get64(Checkpoint[] storage self, uint64 time) internal view returns (uint256) {
        return uint256(get192(self, time));
    }

    function lastUpdated(Checkpoint[] storage self) internal view returns (uint256) {
        uint256 length = self.length;

        if (length > 0) {
            return uint256(self[length - 1].time);
        }

        return 0;
    }

    function getLatestValue(Checkpoint[] storage self) internal view returns (uint256) {
        uint256 length = self.length;
        if (length > 0) {
            return uint256(self[length - 1].value);
        }

        return 0;
    }

    function add192(Checkpoint[] storage self, uint64 time, uint192 value) internal {
        uint256 length = self.length;

        if (length == 0) {
            self.push(Checkpoint(time, value));
        } else {
            Checkpoint storage currentCheckpoint = self[length - 1];
            uint64 currentCheckpointTime = currentCheckpoint.time;
            if (time > currentCheckpointTime) {
                self.push(Checkpoint(time, value));
            } else if (time == currentCheckpointTime) {
                currentCheckpoint.value = value;
            } else { // ensure list ordering
                revert(ERROR_PAST_CHECKPOINT);
            }
        }
    }

    function get192(Checkpoint[] storage self, uint64 time) internal view returns (uint192) {
        uint256 length = self.length;

        if (length == 0) {
            return 0;
        }

        uint256 lastIndex = length - 1;

        // short-circuit
        Checkpoint storage lastCheckpoint = self[lastIndex];
        if (time >= lastCheckpoint.time) {
            return lastCheckpoint.value;
        }

        if (time < self[0].time) {
            return 0;
        }

        uint256 low = 0;
        uint256 high = lastIndex;

        while (high > low) {
            uint256 mid = (high + low + 1) / 2; // average, ceil round
            Checkpoint storage checkpoint = self[mid];
            uint64 midTime = checkpoint.time;

            if (time > midTime) {
                low = mid;
            } else if (time < midTime) {
                high = mid - 1;
            } else { // time == midTime
                return checkpoint.value;
            }
        }

        return self[low].value;
    }
}