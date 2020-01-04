
__join_policy = {'input': ('label', 'alice_verifying_key'),
                    'output': ('policy_encrypting_key', )}

__retrieve = {'input': ('label', 'policy_encrypting_key', 'alice_verifying_key', 'message_kit'),
                'output': ('cleartexts', )}

__public_keys = {'input': (),
                    'output': ('bob_encrypting_key', 'bob_verifying_key')}

specifications = {'join_policy': __join_policy,
                    'retrieve': __retrieve,
                    'public_keys': __public_keys}