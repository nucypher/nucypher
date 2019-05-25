import Vue from 'vue'
import App from './App.vue'
import BootstrapVue from 'bootstrap-vue';
import { VueReCaptcha } from 'vue-recaptcha-v3';
import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-vue/dist/bootstrap-vue.css';

import NuLogo from '@/components/logo';

Vue.use(BootstrapVue);
Vue.use(VueReCaptcha, { siteKey: '6Lf3_qMUAAAAABdhFBVGyA9IYjxMxXw97hLKIphk' })
Vue.component('nu-logo', NuLogo);

Vue.config.productionTip = false

new Vue({
  render: h => h(App),
}).$mount('#app');
