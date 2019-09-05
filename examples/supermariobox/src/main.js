import Vue from 'vue'
import App from './App.vue'

Vue.config.productionTip = false
Vue.config.ignoredElements = ['nucypher']

new Vue({
  render: h => h(App),
}).$mount('#app')
