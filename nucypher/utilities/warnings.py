def render_ferveo_key_mismatch_warning(local_key, onchain_key):
    message = f"""
Local Ferveo public key {bytes(local_key).hex()[:8]} does not match on-chain public key {bytes(onchain_key).hex()[:8]}!

This is a critical error.  Without private keys your node will not be able to provide service for existing DKGs.

If you are relocating your node to a new host you must copy the keystore directory to the new host.

If you do not have a backup of the keystore or have lost your password, you will need to recover your node using the 
recovery phrase by running:

nucypher ursula recover

If you have lost your recovery phrase please open up a support ticket in the Threshold discord server (#taco). 
Your stake may be slashed but the punishment will be significantly smaller if you disclose the loss and a key material
handover is completed quickly, which will restore your node and ensure the service is not disrupted.

"""
    return message
