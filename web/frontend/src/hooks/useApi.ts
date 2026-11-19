import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react'
import { describeError } from '../lib/format'

export interface ApiState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

export function useApi<T>(loader: () => Promise<T>, deps: DependencyList = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    loaderRef.current().then(
      (result) => {
        if (cancelled) return
        setData(result)
        setLoading(false)
      },
      (cause: unknown) => {
        if (cancelled) return
        setError(describeError(cause))
        setLoading(false)
      },
    )

    return () => {
      cancelled = true
    }
    // Callers pass an explicit dependency list; the loader is read through a ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, revision])

  const reload = useCallback(() => setRevision((value) => value + 1), [])

  return { data, error, loading, reload }
}
