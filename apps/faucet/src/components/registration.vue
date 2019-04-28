<template>
    <b-jumbotron class="mechanics" lead="To receive tokens, register your address here">
        <b-form @submit.prevent="onSubmit">
        <b-form-input v-model="address" placeholder="Your address"></b-form-input>
        <b-btn :disabled="!validAddress" class="mt-3" variant="primary" type="submit">ok</b-btn>
        </b-form>
        <b-alert class="mt-3" show v-if="error" variant="danger">{{error}}</b-alert>
        <b-alert class="mt-3" show v-if="success" variant="success">{{address}} successfully registered.</b-alert>
    </b-jumbotron>
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
    };
  },
  methods: {
    onSubmit(){
      http.post('register', { address: this.address }).then((res) => {
        this.error = null;
        this.success = true;
      }).catch((err) => {
        this.success = false;
        if (!err.reponse){
            this.error = "No response from the server.  Try again later."
        } else{
          this.error = err.response.data;
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

<style scoped>


</style>
