import axios from 'axios'

/** Avoid infinite UI spinners when API or DB hangs (browser waits until this elapses). */
const client = axios.create({
  baseURL: '/api',
  timeout: 60_000,
})

client.interceptors.request.use((config) => {
  const id = localStorage.getItem('pxt_user_id')
  if (id) {
    config.headers['X-User-Id'] = id
  }
  return config
})

export default client
