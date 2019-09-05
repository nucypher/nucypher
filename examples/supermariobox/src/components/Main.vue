<template>
  <div class="hello">
      <nu-bit v-for="(pic, index) in getData()" v-bind:key="index" :data="pic"/>
  </div>
</template>

<script>
import data1 from '@/data/data1.json';
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
      /*
        very simple routing... find a number in the url
        either  /#/1 or /2 should work.

        if no number is found, return 0
      */

      let pathdata = []
      if (window.location.href.indexOf('#/')>0){
        pathdata = window.location.hash.split('/');
      } else {
        pathdata = window.location.pathname.split('/');
      }
      if (pathdata.length > 1) {
        return Math.min(parseInt(pathdata[pathdata.length-1]), this.loadedData.length-1);
      }
      return 0;
    }
  },
  data(){
    return {
      loadedData: [
        data1,
      ]
    }
  }
}
</script>
