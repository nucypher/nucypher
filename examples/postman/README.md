## Postman collection

This collection is designed to help in testing the nucypher encryption workflow.
Each item is linked to environment variables that are injected into future calls.

The order to call the collection is as follows

- Alice/derive_policy_pubkey (create a policy)
- Enrico/encrypt_message (encrypt some data inside the policy)
- Bob/public_keys (Get Bob's keys so alice can grant him permission)
- Alice/grant (Grant bob permission to see the policy's data)
- Bob/retrieve (Get alice's data)

If you try to receive the data before you are granted access you will be returned a 500.
