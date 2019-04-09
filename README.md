![](/docs/source/.static/img/nucypher.png)

*A proxy re-encryption network to empower privacy in decentralized systems*

[![pypi](https://img.shields.io/pypi/v/nucypher.svg?style=flat)](https://pypi.org/project/nucypher/)
[![pyversions](https://img.shields.io/pypi/pyversions/nucypher.svg)](https://pypi.org/project/nucypher/)
[![codecov](https://codecov.io/gh/nucypher/nucypher/branch/master/graph/badge.svg)](https://codecov.io/gh/nucypher/nucypher)
[![circleci](https://img.shields.io/circleci/project/github/nucypher/nucypher.svg?logo=circleci)](https://circleci.com/gh/nucypher/nucypher/tree/master)
[![discord](https://img.shields.io/discord/411401661714792449.svg?logo=discord)](https://discord.gg/7rmXa3S)
[![Documentation Status](https://readthedocs.org/projects/nucypher/badge/?version=latest)](https://nucypher.readthedocs.io/en/latest/)
[![license](https://img.shields.io/pypi/l/nucypher.svg)](https://www.gnu.org/licenses/gpl-3.0.html)

----

The NuCypher network facilitates end-to-end encrypted data sharing
for distributed apps and protocols.
Access permissions are baked into the underlying encryption,
and access can only be explicitly granted by the data owner via sharing policies.
Consequently, the data owner has ultimate control over access to their data.
At no point is the data decrypted nor can the underlying private keys be
determined by the NuCypher network.

Under the hood, the NuCypher network uses the [Umbral](https://github.com/nucypher/pyUmbral)
threshold proxy re-encryption scheme to provide cryptographic access control.

# How does NuCypher work?

01. Alice, the data owner, grants access to her encrypted data to
anyone she wants by creating a policy and uploading it to
the NuCypher network.

02. Using her policy's public key, any entity can encrypt data on Alice's behalf.
This entity could be an IoT device in her car, a collaborator assigned
the task of writing data to her policy, or even a third-party creating
data that belongs to her – for example, a lab analyzing medical tests.
The resulting encrypted data can be uploaded to IPFS, Swarm, S3,
or any other storage layer.

03. A group of Ursulas, which are nodes of the NuCypher network,
receive the access policy and stand ready to
re-encrypt data in exchange for payment in fees and token rewards.
Thanks to the use of proxy re-encryption,
Ursulas and the storage layer never have access to Alice's plaintext data.

04. Bob, a data recipient, sends an access request to the NuCypher network.
If Bob was granted an access policy by Alice,
the data is re-encrypted for his public key,
and he can subsequently decrypt it with his private key.

More detailed information:

- Documentation https://nucypher.readthedocs.io/en/latest/
- Website https://www.nucypher.com/


# Whitepapers

### Network

[*"NuCypher - A proxy re-encryption network to empower privacy in decentralized systems"*](https://github.com/nucypher/whitepaper/blob/master/whitepaper.pdf)

*by Michael Egorov, David Nuñez, and MacLane Wilkison - NuCypher*

### Economics

[*"NuCypher - Mining & Staking Economics"*](https://github.com/nucypher/mining-paper/blob/master/mining-paper.pdf)

*by Michael Egorov, MacLane Wilkison - NuCypher*


### Cryptography

[*"Umbral: A Threshold Proxy Re-Encryption Scheme"*](https://github.com/nucypher/umbral-doc/blob/master/umbral-doc.pdf)

*by David Nuñez*

# Getting Involved

NuCypher is a community-driven project and we're very open to outside contributions.

All our development discussions happen in our [Discord server](https://discord.gg/7rmXa3S), where we're happy to answer technical questions, discuss feature requests,
and accept bug reports.

If you're interested in contributing code, please check out our [Contribution Guide](https://docs.nucypher.com/en/latest/guides/contribution_guide.html)
and browse our [Open Issues](https://github.com/nucypher/nucypher/issues) for potential areas to contribute.

Get up and running quickly by using our [docker development setup](dev/docker/README.md)

# Security

If you identify vulnerabilities with _any_ nucypher code, please email security@nucypher.com with relevant information to your findings.
We will work with researchers to coordinate vulnerability disclosure between our stakers, partners, and users to ensure successful mitigation of vulnerabilities.

Throughout the reporting process, we expect researchers to honor an embargo period that may vary depending on the severity of the disclosure.
This ensures that we have the opportunity to fix any issues, identify further issues (if any), and inform our users.

Sometimes vulnerabilities are of a more sensitive nature and require extra precautions.
We are happy to work together to use a more secure medium, such as Signal.
Email security@nucypher.com and we will coordinate a communication channel that we're both comfortable with.

A great place to begin your research is by working on our testnet.
Please see our [documentation](https://docs.nucypher.com) to get started.
We ask that you please respect testnet machines and their owners.
If you find a vulnerability that you suspect has given you access to a machine against the owner's permission, stop what you're doing and immediately email security@nucypher.com.


