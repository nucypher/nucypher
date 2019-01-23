# Local Development Fleet Testing

## Overview

*Note: Currently only "Federated Only" mode is supported for local fleets*

All Demo Ursulas:
 * Run on `localhost`
 * In `--federated-only` mode
 * On the `TEMPORARY_DOMIAN` (Implied by `--dev`)
 * Using temporary resources (files, database, etc.)


## Running A Local Fleet

### 1. Install Nucypher

Acquire the nucypher application code and install the dependencies;
For a full installation guide see the [NuCypher Installation Guide](../guides/installation_guide)

### 2. Run a Lonely Ursula

The first step is to launch the first Ursula on the network by running:

`$ python run_lonely_demo_ursula.py`

This will start an Ursula node:
 * With seednode discovery disabled
 * On port `11500`

### 3. Run a Local Fleet of Ursulas

Next, launch subsequent Ursulas, informing them of the first Ursula:

`$ python run_demo_ursula_fleet.py`

This will run 5 temporary Ursulas:
 * All specify the lonely Ursula as a seednode
 * Run on ports `11501` through `11506`

### 4. Run an Entry-Point Ursula (Optional)

While the local fleet is running, you may want an entry-point to introspect the code in a debugger.
For this we provide the optional script `run_single_demo_ursula.py` for your convenience.

`$ python run_single_demo_ursula.py`

This will run a single temporary Ursulas:
 * Specifies a random fleet node as a teacher
 * On a random available port

## Connecting the the Local Fleet

Alternately, you can connect any node run from the CLI by specifying one of the nodes
in the local fleet as a teacher, the same network domain, and the same operating mode:

`nucypher ursula run --dev --teacher-uri localhost:11501`
