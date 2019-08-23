<template>
  <div id="app">
    <Logo style="width:300px" :hide-logo="false" :hide-text="false"/>
    <Main/>
  </div>
</template>

<script>
import Main from './components/Main.vue';
import Logo from './components/NuCypherLogo.vue'

export default {
  name: 'app',
  components: {
    Main,
    Logo,
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
</style>
