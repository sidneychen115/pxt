import axios from 'axios'

/** FastAPI `HTTPException` detail from axios error responses. */
export function apiErrorMessage(err: unknown, fallback = '请求失败'): string {
  if (err instanceof Error && !(axios.isAxiosError(err) && err.response)) {
    return err.message
  }
  if (axios.isAxiosError(err) && err.response?.data != null) {
    const data = err.response.data
    if (typeof data === 'string') return data
    if (typeof data === 'object' && data !== null && 'detail' in data) {
      const detail = (data as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        return detail
          .map(d => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
          .join('; ')
      }
    }
  }
  return fallback
}
