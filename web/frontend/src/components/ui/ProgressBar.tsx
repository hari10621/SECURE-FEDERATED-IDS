export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0))
  const percent = Math.round(clamped * 100)
  return (
    <div>
      {label ? (
        <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
          <span className="text-muted">{label}</span>
          <span className="font-mono text-ink">{percent}%</span>
        </div>
      ) : null}
      <div
        className="h-2 overflow-hidden rounded-full bg-navy-800"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={label ?? 'Progress'}
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-deep to-cyan-glow transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}
