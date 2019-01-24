# Finnegan's Wake Demo

## Overview

This demo is an example of a NuCypher decentralized network allowing Alice to share
data with Bob using proxy re-encryption. This enables the private sharing of data between
participants in public consensus networks, without revealing data keys to intermediary entities.

|Step|Character|Operation                                                                                    |
|----|---------|---------------------------------------------------------------------------------------------|
|1   |Alice    |Alice sets a Policy on the NuCypher network (2/3) and grants access to Bob                   |
|2   |Alice    |Label and Alice's key public key provided to Bob                                             |
|4   |Bob      |Bob joins the policy with Label and Alice's public key                                       |
|5   |Enrico   |DataSource created for the policy                                                            |
|6   |Enrico   |Each plaintext message gets encapsulated through the DataSource to messageKit                |
|5   |Bob      |Bob receives and reconstructs the DataSource from Policy public key and DataSource public key|
|6   |Bob      |Bob retrieves the original message form DataSource and MessageKit                            |


## 1. Install Nucypher

Acquire the nucypher application code and install the dependencies;
For a full installation guide see the [NuCypher Installation Guide](../guides/installation_guide)

## 2. Download the Book Text
`./download_finnegans_wake.sh`

## 3. Run the Demo
`python3 finnegans-wake-concise-demo.py`
