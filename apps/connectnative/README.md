# Install instructions.


## Firefox
1. do a `pipenv shell` in your NuCypher repo directory
2. run a `pipenv install .`
    *  this will install the cli executable in your bin/path
3. run the install script
    *  `python3 apps/connectnative/install/firefox.py`
    *  this will put native manifest needed by firefox in all the right places. as seen here: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_manifests
4.  Go into firefox and load the extension
    *  https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Your_first_WebExtension#Installing
    * you can select any file in this directory
5. That should be all!

