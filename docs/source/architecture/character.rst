.. _character-concepts:

Character Concepts
==================

NuCypher's API is written as characters within a cryptological narrative/archetype, each fulfilling a particular
role.

* **Alice**:  *"The Data Owner"* - retains full control over the data encrypted for her and determines whom to share the data with
* **Enrico**: *"The Encryptor"* - a data source that encrypts data on behalf of Alice
* **Bob**:    *"The Data Recipient"* - the data recipient that Alice intends to share data with
* **Ursula**: *"The Proxy in PRE"* - the PRE node on the Threshold Network that stands ready to re-encrypt data in exchange for payment in fees and token rewards; they enforce the access policy created by Alice

.. _Umbral: https://github.com/nucypher/umbral-doc/blob/master/umbral-doc.pdf


.. raw:: html

    <div>
        <div style="position:relative;padding-top:56.25%;">
            <iframe style="position:absolute;top:0;left:0;width:100%;height:100%;" src="https://www.youtube-nocookie.com/embed/SXn1zShgVI8?rel=0&controls=1&modestbranding=1" frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
   </div>
   <br/>


Character Actions
-----------------

Alice::Grant
^^^^^^^^^^^^

.. image:: ../.static/img/alice_grant.svg
    :target: ../.static/img/alice_grant.svg

Alice has data that she wants to share and she wants to classify/categorize
her data according to how she intends to share it. These subsets of data would have their own set of permissions - within NuCypher
this concept is called a `label`. Alice uses this `label`  to categorize data and she creates an asymmetric encryption key
for Enrico characters based on the `label`. For example, Alice may use different `labels` and different Enricos for
health data, personal data, and work-related data. Essentially, `labels` are a way to categorize data for sharing - you
can think of file system folders as being somewhat analogous to `labels`. Alice can delegate access permissions to
the encrypted data classified under a `label` to any recipient she sees fit.

The same encryption key can be used by Enrico even though multiple policies for the data can be created
for different Bobs. Enrico, therefore, only has to encrypt data using the provided encryption key
and data can later be re-encrypted for all Bobs who have been granted access.

When Alice wants to share this information with Bob, she can create a
policy in the PRE Application running on the Threshold Network to grant access to him. To grant access to Bob, Alice must:

#. Create a re-encryption key based on the asymmetric private key and Bob's public key
#. Determine `n` Ursulas from the Threshold Network to use in the policy
#. Configure the conditions of the policy, e.g. *expiration time, m-of-n threshold values*
#. Deploy the policy to the blockchain and escrow associated policy fees
#. Create a `treasure map`, encrypted for Bob that contains the list of `n` Ursulas in the policy,
   and the `n` re-encryption key fragments (`kFrags`), each encrypted for a different Ursula in
   the policy.

   .. note::

      Bob can decrypt the encrypted treasure map, but since each re-encryption fragment is encrypted
      for a specific Ursula, Bob never has access to any re-encryption fragment in plaintext form.


Enrico::Encrypt
^^^^^^^^^^^^^^^

.. image:: ../.static/img/enrico_encrypt.svg
    :target: ../.static/img/enrico_encrypt.svg

The Ursulas uses the Umbral_ threshold proxy re-encryption scheme which employs a key encapsulation mechanism (KEM)/data
encapsulation mechanism (DEM). In this approach, an ephemeral symmetric key is used to encrypt the data, and the
symmetric key is encrypted using an asymmetric encryption key. The encrypted data (the DEM portion) and the
encrypted symmetric key (the KEM portion, called a `capsule`) are stored together.

Even though different blocks of newly generated bulk data may use different symmetric keys, the same asymmetric
encryption key provided by Alice is used to encrypt the symmetric key. How and when Enrico uses a new symmetric key
is up to the user of the Enrico API.


Bob::Retrieve
^^^^^^^^^^^^^

.. image:: ../.static/img/bob_retrieve.svg
    :target: ../.static/img/bob_retrieve.svg

When Bob wants to access the data, he must first obtain the encrypted data and `capsule` from encrypted storage.
However, this data is currently encrypted and inaccessible to Bob.

To gain access, Bob must request re-encryption of the `capsule` by the `n` Ursulas that participated in the policy.
Remember that when Alice granted access to Bob, she created a `treasure map` that contained
this list of `n` Ursulas in the policy, and the associated encrypted re-encryption key fragments (`kFrags`) for Bob to
give to the Ursulas for the re-encryption operation. Therefore, Bob sends his `capsule` and the relevant encrypted
`kFrag` to the various Ursulas in the Threshold Network associated with the policy. Those Ursulas
will decrypt the encrypted `kFrag` and use it to perform a partial re-encryption operation on the `capsule` to
produce a corresponding ciphertext fragment, `cFrag`. In the same way a `kFrag` is a fragment of a key, a `cFrag`
is a fragment of ciphertext. The `cFrag` is returned to Bob, who collects `cFrags` until he obtains a threshold, `m`,
number of `cFrags`. Bob attaches `m` received `cFrags` to the original `capsule` to obtain the fully re-encrypted
`capsule` that is now encrypted under his public key. Note that the generation of a complete re-encrypted `capsule`
is possible from a smaller number of `cFrags` than the number of `kFrags` included in the `treasure map`
(m-of-n threshold scheme). Bob can now decrypt the `capsule` to obtain the symmetric key originally used to
encrypt the bulk data.

Once Bob has the symmetric key, he can use it to decrypt the bulk data. This process can be repeated as more data is
shared with Bob that is associated with the `label` for the policy.

Ultimately, because of the KEM/DEM approach, only the `capsule` needs to be re-encrypted for Bob.
Subsequently, the size of the actual bulk data is irrelevant - whether 1KB or 1GB the re-encryption operation only
needs to be performed on the fixed size `capsule`, which is simply an encrypted symmetric key.


Ursula::Reencrypt
^^^^^^^^^^^^^^^^^

.. image:: ../.static/img/ursula_reencrypt.svg
    :target: ../.static/img/ursula_reencrypt.svg

Having received an encrypted `kFrag` and a `capsule` from Bob as part of the re-encryption request,
Ursula can now partially re-encrypt data for Bob. Ursulas decrypt the encrypted `kFrag` using their private key, and
use it to perform a re-encryption operation on the `capsule` to return a corresponding `cFrag`. Bob will
require `m` of these interactions with `m` different Ursulas to obtain a fully re-encrypted `capsule`.
