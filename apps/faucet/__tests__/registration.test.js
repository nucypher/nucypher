/* eslint-disable no-undef */
import registration from "@/components/registration.vue";

describe("registration.vue", () => {
  it("validates ethereum addresses", () => {
    const data = { address: "0xDbc23AE43a150ff8884B02Cea117b22D1c3b9796" };
    expect(registration.computed.validAddress.call(data)).toBeTruthy();
  });
});