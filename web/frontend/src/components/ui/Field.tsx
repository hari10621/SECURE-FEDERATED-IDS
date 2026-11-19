import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { cn } from '../../lib/format'

const CONTROL =
  'w-full rounded-lg border border-line bg-navy-950/70 px-3 py-2 text-sm text-ink placeholder:text-faint ' +
  'transition-colors hover:border-navy-700 focus:border-cyan-glow focus:outline-none ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string
  htmlFor: string
  hint?: ReactNode
  error?: string | null
  required?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-ink">
        {label}
        {required ? (
          <span className="ml-1 text-cyan-glow" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-red-300" id={`${htmlFor}-error`}>
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs leading-5 text-faint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(CONTROL, className)} />
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn(CONTROL, 'appearance-none pr-8', className)} />
}

export function TextArea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(CONTROL, 'min-h-24 font-mono text-xs', className)} />
}
