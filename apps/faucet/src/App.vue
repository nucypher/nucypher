<template>
  <b-container fluid>
    <b-nav>
      <b-nav-item>
        <div class="mt-3" style="width:100px">
          <a href="https://www.nucypher.com">
            <nu-logo/>
          </a>
        </div>
      </b-nav-item>
      <b-nav-item>
        <div class="mt-3">
          <a target="_blank" href="/">
            <h4>Felix</h4>
          </a>
        </div>
      </b-nav-item>
      <b-nav-item>
        <div class="mt-3">
          <a target="_blank" href="http://23.20.196.108:3000">
            <h5>eth-stats <div style="width:30px;display:inline-block"><nu-logo/></div></h5>
          </a>
        </div>
      </b-nav-item>
    </b-nav>
    <felix/>
    <b-row class="bottom">
      <b-col style="min-height:400px" cols="12">
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import felix from './pages/felix.vue'

export default {
  name: 'app',
  components: {
    felix
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
