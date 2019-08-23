const nucypher = browser.runtime.connectNative("nucypher");

const decrypt = (encrypted, key) => {
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
  return base64DecryptedMessage;
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

const fromHexString = hexString =>
  new Uint8Array(hexString.match(/.{1,2}/g).map(byte => parseInt(byte, 16)))

nucypher.onMessage.addListener((response) => {
  // response is a key which can be used to decrypt the original image.
  console.log("Received: " + response);
  //decrypt here
  portFromCS.postMessage(response);
});

var portFromCS;

function connected(p) {
  portFromCS = p;
  portFromCS.onMessage.addListener(ncRetrieve);
}

browser.runtime.onConnect.addListener(connected);

