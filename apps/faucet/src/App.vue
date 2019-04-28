<template>
  <b-container fluid>
    <b-nav>
      <b-nav-item>
        <div class="mt-3" style="width:100px">
          <a target="blank" href="https://www.nucypher.com">
            <nu-logo/>
          </a>
        </div>
      </b-nav-item>
    <b-nav-item><h4 class="mt-3">Felix</h4></b-nav-item>
    </b-nav>
    <b-row class="justify-content-md-center">
      <b-col md="4">
        <p>
          Felix distributes tokens on the NuCypher test net.
        </p>
      </b-col>
      <b-col md="8">
        <Registration/>
      </b-col>
    </b-row>
    <b-row class="bottom">
      <b-col style="min-height:400px" cols="12">
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import Registration from './components/registration.vue'

export default {
  name: 'app',
  components: {
    Registration
  }
}
</script>

<style>
#app {
  font-family: 'Avenir', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}
.bottom {
  background-image: url("assets/bg.png");
  background-repeat: repeat-x;
  background-size: cover;
}
</style>
