
const nucypher = browser.runtime.connectNative("nucypher");

nucypher.onMessage.addListener((response) => {
  console.log("Received: " + response);
});

browser.browserAction.onClicked.addListener(() => {
  const data = {
    character: "bob",
    action:"retrieve",
    args: {
      "teacher": "https://165.22.21.214:9151",
      "label": "damon_test_1",
      "message-kit": "AkHV6LZ0WwBUhPWLXkyc3FurlemkJ1q3O7AZBvb0LzXOAvxN2fOmOqOSZLwFFsUJXQ2qY7wf4jLm3GRxNQ3POmdo/x6Ix/3GjQ1B/Dp8IuhC/vEDEFjTBAQjhAUnmrupGYEDJlAyK+h3YTYSAOpyUX1OUQM1e/lTViWS2Ea0GcM3fmpBCw+l15p5Rk9fWnCAtu4qA45IVwCqTo3FMHwsrxl3UGU5aM6w5Jyd961mmrMMYxyqwLvlenjabOGbe4T51vqqtZpfyVhVYK1QCdqIXbrS6tdoUOc601UCUlmSVGJp6Z26B+3fneNcJJZYWhaQO4LPq0KREZVnekecJ4uy",
      "policy-encrypting-key": "032ceda4de0c68450aaa51354abb0e657c00da38e08212beab44bf8b790258f6c9",
      "alice-verifying-key": "0341bcb12a5d99f752581af7cd8ca39f7d46737d2f9b7cbe95d2eb40c5c75dee67",
    },
  };
  console.log(data);
  nucypher.postMessage(data);
});
