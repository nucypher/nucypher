# NuCypher's Heartbeat Demo using Character Control

![Heartbeat Demo](assets/heartbeat_demo_overview.png)

**NOTE: This demo is different from the other Heartbeat Demo in that it utilizes Character Control REST endpoints to 
execute `nucypher` functions. Even though this demo is written in python, these same Character Control REST endpoints 
can be used by non-python applications to utilize `nucypher` functionality.**

Alicia has a Heart Monitor device that measures her heart rate and outputs this data in encrypted form. Since she 
thinks that she may want to share this data in the future, she uses NuCypher to create a _policy public key_ for the 
Heart Monitor to use, so she can read and delegate access to the encrypted data as she sees fit. The Heart Monitor 
uses this public key to produce a database with some amount of encrypted heart rate measurements; this database can 
be located on some storage service (e.g., IPFS, S3, whatever). 

At some moment, she wants to share this information with other people, such as her Doctor. Once she obtains her 
Doctor's public key, she can create a policy in the NuCypher network granting access to him. After this, her Doctor 
can read the encrypted database (which was populated by the Heart Monitor) and request a re-encrypted ciphertext for 
each measurement, which can be decrypted with the Doctor's private key.

This simple use case showcases many interesting and distinctive aspects of NuCypher:
  - Alicia can create policy public keys **before knowing** who can be potential consumers.
  - Alicia, or anyone knowing the policy public key (e.g., the Heart Monitor), can produce encrypted data that belongs 
  to the policy. Again, this can happen before granting access to any consumer.
  - As a consequence of the previous point, Enricos/Data Sources, like the Heart Monitor, are completely unaware of the 
  recipients. In their mind, they are producing data **for Alicia**.
  - Alicia never interacts with the Doctor: she only needs the Doctor's public key.
  - Alicia only interacts with the NuCypher network to grant access to the Doctor. After this, she can even 
  disappear from the face of the Earth.
  - The Doctor never interacts with Alicia or the Heart Monitor, and only needs the encrypted data and policy metadata.

### How to run the demo
#### Installation of nucypher
See the [installation guide](http://docs.nucypher.com/en/latest/guides/installation_guide.html) for nucypher.

#### Run local node/fleet of nodes
Install dependencies (only for the first time): <http://docs.nucypher.com/en/latest/guides/installation_guide.html#pipenv-development-installation>

(After previously running `pipenv shell`)
For the demo, you can run either a single node, in which case m-of-n can only be 1-of-1 **OR** you can run a fleet 
of nodes where m,n can be greater than 1. See [local fleet instructions](https://docs.nucypher.com/en/latest/demos/local_fleet_demo.html) 
for more information.

#### Run the demo
Since the Character Control REST endpoints are used in this demo, the individual character control services will need
to be executed at different times throughout the demo.

1. Start the Demo UI

    Assuming you already have `nucypher` installed and a local demo fleet of Ursulas deployed:
    
    (after running `pipenv shell`)
    Start the demo:
    ```sh
    (nucypher)$ python examples/heartbeat_rest_ui/char_control_heartbeat.py
    ```
    
    The UI can now be viewed in your browser at [http://127.0.0.1:8050/](http://127.0.0.1:8050/). 
    The characters are provided as links which open in a new tab. These characters will interact with the REST 
    endpoints to use the `nucypher` functionality.

2. Start Alice REST Endpoint in a separate terminal with `nucypher` installed.

    (after running `pipenv shell`)
    ```sh
    (nucypher) nucypher alice run --dev --federated-only --teacher-uri <ursula_teacher_uri>
    ```

3. In the browser UI, open Alicia's tab and click `Create Policy`. Alicia will now use the Alice REST 
    endpoint to create a policy encrypting key.

4. Use the policy public key output from Alicia's tab to start Enrico in a separate terminal with `nucypher` 
    installed.
   
    (after running `pipenv shell`)
    ```sh
    (nucypher) nucypher enrico run --policy-encrypting-key <policy_public_key_hex>
    ```
    
5. Now that Enrico's endpoint has been started, in the browser UI, open Enrico's tab 
   and click `Start Monitoring`.
   
    This starts the collection of heartbeats from Alicia and stores them encrypted with the policy key in a database.
   
6. Alicia can now grant access to Bob. So Bob's endpoint should be started in a separate terminal with `nucypher` 
    installed.

    (after running `pipenv shell`)
    ```sh
    (nucypher) nucypher bob run --federated-only --dev --teacher-uri <ursula_teacher_uri>
    ```
  
7. Now that Bob's endpoint is available, in the browser UI, go to Alicia's page to grant access to 
   Bob. Bob's verifying and encryption key can be obtained from the terminal that Bob's endpoint was run on in step #6.
   The keys are printed early in the terminal output when Bob's endpoint was started.

    For example (Bob):
    ```sh
    ...
    Starting Learning Loop.
    Starting Bob Character Control...
    Bob Verifying Key 028775469d2408c69c8a5002a5f0f89923c4ecef363e15362ce47e1472727c4ea2
    Bob Encrypting Key 02a647d1e8d60cf7b7e126ff98d2105410d9111a25a665d58428b3721c309f2318
    Site starting on 11151
    ...
    ```
    provides Bob's keys, and his port (11151) which will be needed
    
   One the information has been entered, click on `Grant Access` and then a resulting message confirming access 
   was granted should be displayed.

8. Now that Bob has been granted access to the encrypted heartbeats, he can view them. In 
    the browser UI, open Bob's tab. Enter the required information and then click `Read Heartbeats`. Note,
    the relevant keys can be obtained from the corresponding character REST endpoint terminal by scrolling up to 
    when it was started.
    
    For example: (Alice)
    ```sh
    ...
    Starting Learning Loop.
    Starting Alice Character Control...
    Alice Verifying Key 03f23d16f02ad9f23b6e19b23abc1230334a13ad41774f35b75e77f5bbccc12a39
    ...
    ```
    provides Alicia's verifying key.
    
    For example: (Enrico)
    ```sh
    ...
    Starting Enrico Character Control...
    Enrico Verifying Key 0349461d1ccd4e8e9eb63bf61f2033c7590630e59800a7431216aac8a71f7ce77b
    Site starting on 5151
    ...
    ```
    provides Enrico's verifying key.
    
    In the Bob tab in the UI, Bob should now be plotting the re-encrypted heartbeats into a graph.


**NOTE: The Character REST endpoints provide functionality to request the relevant keys for the corresponding 
characters but this demo does not use them to explicitly clarify what information needs to be provided to each 
character for relevant functionality. The copy-paste done in this demo could be replaced by proving side-channel 
capabilities.**