export const IS_PROD = process.env.NODE_ENV === 'production'

export const API_URL = IS_PROD ? 'https://3.92.28.209' : 'http://localhost:6151/'
