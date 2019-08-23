<template>
  <div class="hello">
      <nu-bit v-for="(pic,index) in getData()" v-bind:key="index" :data="pic"/>
  </div>
</template>

<script>
import data3 from '@/data/data3.json';
import data4 from '@/data/data4.json';
//import data5 from '@/data/data5.json';
//import data6 from '@/data/data6.json';

import NuBit from '@/components/NuBit';

export default {
  name: 'Main',
  components: {
    NuBit,
  },
  props: {
    msg: String
  },
  methods:{
    getData(){
      return this.loadedData[this.getDataIndex()];
    },
    getDataIndex(){
      const pathdata = window.location.pathname.split('/');
      if (pathdata.length > 1) {
        return Math.min(parseInt(pathdata[pathdata.length-1]), this.loadedData.length-1);
      }
      return 0;
    }
  },
  data(){
    return {
      loadedData: [
        data3,
        data4,
        //data5,
        //data6,
      ]
    }
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>
h3 {
  margin: 40px 0 0;
}
ul {
  list-style-type: none;
  padding: 0;
}
li {
  display: inline-block;
  margin: 0 10px;
}
a {
  color: #42b983;
}
</style>
