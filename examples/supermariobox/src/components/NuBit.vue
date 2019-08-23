<template>
  <nucypher :data-data="stringify(data)">
  </nucypher>
</template>

<script>
export default {
    methods:{
      stringify(data){
        return JSON.stringify(data);
      },
    },
    props:['data'],
    name: "NuBit",
}
</script>

<style>

</style>