const nucypher = browser.runtime.connectNative("nucypher");

function ncRetrieve(request) {

  let args = {
    "teacher": "https://165.22.21.214:9151",
  };

  args = Object.assign(args, request);

  delete args['image_ciphertext']

  const data = {
    character: "bob",
    action:"retrieve",
    args,
  };
  console.log('retrieving from bob:', data);
  nucypher.postMessage(data);
};

nucypher.onMessage.addListener((response) => {
  // response is a key which can be used to decrypt the original image.
  portFromCS.postMessage({
    route: 'retrieved',
    data: response,
  });
});

var portFromCS;

function Dispatcher(message){
  const callbacks = {
    'retrieve': ncRetrieve,
  }
  return callbacks[message.route](message.data);
}

function connected(p) {
  portFromCS = p;
  portFromCS.onMessage.addListener(Dispatcher);
}

browser.runtime.onConnect.addListener(connected);

