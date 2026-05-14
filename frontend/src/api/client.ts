import axios from 'axios'

/** Avoid infinite UI spinners when API or DB hangs (browser waits until this elapses). */
const client = axios.create({
  baseURL: '/api',
  timeout: 60_000,
})
export default client
