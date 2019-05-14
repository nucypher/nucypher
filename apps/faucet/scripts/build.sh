#!/usr/bin/env bash
vue-cli-service build;
mv -v ./dist/js/app.*.js ./dist/js/app.js
mv -v ./dist/js/app.*.js.map ./dist/js/app.js.map

echo `sed -E 's/app\.[0-9|a-z]+\.js/app.js/g' < dist/index.html` > dist/index.html



