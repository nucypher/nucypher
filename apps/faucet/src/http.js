import axios from 'axios'

import { API_URL } from '@/constants.js';


const baseConfig = {
  baseURL: API_URL,
}

const http = axios.create(baseConfig);

export default http;

