# Local Development Fleet Testing

![.](https://lh3.googleusercontent.com/u7OEMBBCZjPEZunlVJFC5kR7_2k2FEJWnkzQEB_P0JW-28wtmhFJbE_7M5Ludcuh9yJKXpM8ENKV3QXT4xq3ZGLbzGQMxSm6emo_rR0vLJBnXy0-LiwXPExIDE9F0bSbPV-27bKSS5Rohyl5magLvmFvYRZr9w7MUnoGifhLma0EpQBsRpiTJRVat8ceoxj-7xN3SA9_7BmvuzCbs6xj4KjMAzjkEEaW4t52KSmMeP3X_dc6GbCkIdo1t13Vg09bC5k1kyAYStrbgXx2wWiA5p3N_9TISWgTez4A2Wn1f36DB8V-sOCp5w51u9sUWjGtXZCWsFuUWtB7e3Far2SAnaOYfFNmf4cn0q81R9u5YannkZberqPT9MEhhJA7PRbB1NRRI4a5N_406NoyQlSZHXweC-KQ74Vn147BmJ3UeZETKILCUGk8OpD_qUZ89Rz3R1HUoSpvO9fDIHeZbcB-KXE-wCIRXynMgOunQWP5vy_nZj8mMeOIzlMxorC2uUotToNfjZFPRbMPflz_z-5jE6aYIWf7d8OOgUbOKp_Rw9dJDpZYJAIfwVglYPYMQUyRkkpNzApS6QJCpGtOh_c-b5Kc1mFUpyD-BO3KLHKorNdH1Pnq15D1rLZ8JQ-WjsGDkMEUsndLQt8giYU5hY5NQGg8wMN8LduFZlfi0uRHEc9LiiBmCJCtZ6Fcvltk1WAhhf0k5gpAUwKIogko9w=w1308-h982-no)

## Overview

``` note:: Currently only "Federated Only" mode is supported for local fleets
```

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

This will run 5 temporary Ursulas that:
 * All specify the lonely Ursula as a seednode
 * Run on ports `11501` through `11506`

### 4. Run an Entry-Point Ursula (Optional)

While the local fleet is running, you may want an entry-point to introspect the code in a debugger.
For this we provide the optional script `run_single_demo_ursula.py` for your convenience.

`$ python run_single_demo_ursula.py`

This will run a single temporary Ursula:
 * That specifies a random fleet node as a teacher
 * On a random available port

## Connecting to the Local Fleet

Alternately, you can connect any node run from the CLI by specifying one of the nodes
in the local fleet as a teacher, the same network domain, and the same operating mode,
by default nodes started with the `--dev` flag run on a dedicated domain (`TEMPORARY_DOMAIN`) and
on a different port then the production default port (`9151`).
Local fleet Ursulas range from ports `11500` to `11506` by default.

Here is an example of connecting to a node in the local development fleet:

`nucypher ursula run --dev --teacher-uri localhost:11501`

``` note:: The local development fleet is an *example* meant to demonstrate how to design and use your own local fleet.
```
