const nucypher = browser.runtime.connectNative("nucypher");

const fromHexString = hexString =>
  new Uint8Array(hexString.match(/.{1,2}/g).map(byte => parseInt(byte, 16)))

const decrypt = (data) => {
  let key = data.key;
  let encrypted = data.image;
  const keyUint8Array = fromHexString(key);
  const messageWithNonceAsUint8Array = naclUtil.decodeBase64(encrypted);
  const nonce = messageWithNonceAsUint8Array.slice(0, nacl.secretbox.nonceLength);
  const message = messageWithNonceAsUint8Array.slice(
    nacl.secretbox.nonceLength,
    encrypted.length
  );

  const decrypted = nacl.secretbox.open(message, nonce, keyUint8Array);

  if (!decrypted) {
    console.log("Could not decrypt message");
  }

  const base64DecryptedMessage = naclUtil.encodeUTF8(decrypted);
  portFromCS.postMessage({
    route: 'decrypted',
    data: {
      image: base64DecryptedMessage,
      id: data.id,
    }
  });
};

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
    'decrypt': decrypt,
    'retrieve': ncRetrieve,
  }

  return callbacks[message.route](message.data);
}

function connected(p) {
  portFromCS = p;
  portFromCS.onMessage.addListener(Dispatcher);
}

browser.runtime.onConnect.addListener(connected);

