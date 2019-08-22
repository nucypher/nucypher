<template>
  <div class="hello">
    {{loadedData}}
    <hr>
    {{getData()}}
  </div>
</template>

<script>
import jsondata from '@/data/datasource.json';

export default {
  name: 'HelloWorld',
  props: {
    msg: String
  },
  methods:{
    getData(){
      const pathdata = window.location.pathname.split('/');
      return pathdata.length > 1? this.loadedData[
        parseInt(
          pathdata[pathdata.length-1]
        )] : this.loadedData[0];
    },
  },
  data(){
    return {
      loadedData: jsondata,
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
