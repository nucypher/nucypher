# PRE Finnegan's Wake Demo

This illustrates Alice sharing data with Bob over the Threshold Network using TACo's proxy re-encryption (PRE),
without revealing private keys to intermediary entities.

First, configure the demo by making exporting environment variables
with your provider and wallet details.

```bash
export DEMO_L1_PROVIDER_URI=<YOUR ETH PROVIDER URL>
export DEMO_L2_PROVIDER_URI=<YOUR POLYGON PROVIDER URL>
export DEMO_L2_WALLET_FILEPATH=<YOUR WALLET FILEPATH>
export DEMO_ALICE_ADDRESS=<YOUR ALICE ETH ADDRESS>
```

Alternatively you can use the provided .env.template file by making a copy named .env
and adding your provider and wallet details.  To set the variables in your current session run:
`export $(cat .env | xargs)`

Optionally, you can change the network the demo is running on by changing the value of `L1_NETWORK` and `L2_NETWORK`.
If you change these values be sure to also change `L1_PROVIDER_URI` and `L2_PROVIDER_URI` accordingly.

Available options for `TACO_NETWORK` are `lynx`, `tapir` or `mainnet`.

Ensure Alice's account has a bit of MATIC on polygon to pay for the policy.

Subsequently, to execute the demo run:
`python3 finnegans-wake-demo-l2.py`

For more detailed logging change the value of `LOG_LEVEL` to `'debug'`.
