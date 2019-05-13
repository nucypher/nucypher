export const IS_PROD = (window.location.host.indexOf('localhost') + window.location.host.indexOf('127.0.0.1')) < -1;
export const API_URL = IS_PROD ? 'http://3.92.28.209:6151' : 'http://localhost:6151/'
