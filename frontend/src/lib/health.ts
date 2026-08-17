export type HealthStatus = 'ok' | 'error' | 'unreachable'

export async function checkHealth(): Promise<HealthStatus> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  try {
    const response = await fetch(`${baseUrl}/health`)
    if (!response.ok) return 'error'
    const data = await response.json()
    return data.status === 'ok' ? 'ok' : 'error'
  } catch {
    return 'unreachable'
  }
}
