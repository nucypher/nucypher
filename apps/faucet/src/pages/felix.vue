<template>
    <b-container>
        <b-row class="justify-content-md-center">
            <b-col md="4">
                <p>
                Felix distributes tokens and ether on NuCypher testnets.
                </p>
            </b-col>
            <b-col md="8">
                <b-jumbotron class="mechanics" lead="To receive tokens, register your address here:">
                    <b-form @submit.prevent="recaptcha">
                        <b-form-input v-model="address" placeholder="Your address"></b-form-input>
                        <b-row style="min-height:6em">
                            <b-col cols="3">
                                <b-btn :disabled="!validAddress" class="mt-3" variant="primary" type="submit">Register</b-btn>
                            </b-col>
                            <b-col cols="9">
                                <b-alert class="mt-2"  :show="dismissCountDown" dismissible fade @dismissed="dismissCountDown=0" v-if="error" variant="danger">{{error}}</b-alert>
                                <b-alert class="mt-2" show v-if="success" variant="success">{{address}} successfully registered.</b-alert>
                            </b-col>
                        </b-row>
                    </b-form>
                </b-jumbotron>
            </b-col>
        </b-row>
    </b-container>
</template>

<script>
import http from '@/http';
import { checkAddressChecksum } from 'web3-utils';

export default {
  data() {
    return {
      address: '',
      success: false,
      error: null,
      dismissCountDown: 0,
    };
  },
  methods: {
    recaptcha() {
      this.$recaptcha('register').then((token) => {
        this.onSubmit(token);
      })
    },
    onSubmit(token){
      http.post('register', { address: this.address, captcha: token }).then(() => {
        this.error = null;
        this.success = true;
      }).catch((err) => {
        this.success = false;
        this.dismissCountDown = 5;
        if (err.response !== undefined) {
          if (err.response.data){
            if (err.response.data.indexOf('DOCTYPE HTML') >= 0){
              this.error = err.response.statusText;
            } else {
              this.error = err.response.data;
            }
          }
        } else{
          this.error = "No response from the server.  Try again later."
        }
      });
    },
  },
  computed: {
    validAddress() {
      if (this.address.length >= 40) {
        return checkAddressChecksum(this.address);
      }
      return false;
    },
  },
}
</script>

<style>

</style>
