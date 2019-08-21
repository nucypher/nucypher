/*
On startup, connect to the "nucypher" app.
*/
var port = browser.runtime.connectNative("nucypher");


/*
Listen for messages from the app.
*/
port.onMessage.addListener((response) => {
  console.log("Received: " + response);
});

/*
On a click on the browser action, send the app a message.
*/
browser.browserAction.onClicked.addListener(() => {


  const data = {
    character: "bob",
    action: "retrieve",

    // __retrieve = (('label', 'policy_encrypting_key', 'alice_verifying_key', 'message_kit'),
                  // ('cleartexts', ))
  };

  var out = JSON.stringify(data);
  console.log(out);
  port.postMessage(data);
});
