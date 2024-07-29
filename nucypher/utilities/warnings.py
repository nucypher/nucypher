def render_ferveo_key_mismatch_warning(local_key, onchain_key):
    message = f"""

ERROR: The local Ferveo public key {bytes(local_key).hex()[:8]} does not match the on-chain public key {bytes(onchain_key).hex()[:8]}!

This is a critical error. Without the original private keys, your node cannot service existing DKGs.

IMPORTANT: Running `nucypher ursula init` will generate new private keys, which is not the correct procedure
for relocating or restoring a TACo node.

To relocate your node to a new host copy the keystore directory (~/.local/share/nucypher) to the new host.
If you do not have a backup of the original keystore or have lost your password, you will need to recover your 
node using the recovery phrase assigned during the initial setup by running:

nucypher ursula recover

If you have lost your recovery phrase: Open a support ticket in the Threshold Discord server (#taco).
Disclose the loss immediately to minimize penalties. Your stake may be slashed, but the punishment will be significantly
reduced if a key material handover is completed quickly, ensuring the node's service is not disrupted.

"""
    return message
