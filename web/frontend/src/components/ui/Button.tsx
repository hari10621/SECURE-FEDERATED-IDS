import { Loader2 } from 'lucide-react'
import { useId, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../lib/format'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'border-cyan-deep bg-cyan-deep text-navy-950 hover:border-cyan-glow hover:bg-cyan-glow',
  secondary:
    'border-line bg-navy-800 text-ink hover:border-cyan-glow/50 hover:bg-navy-700',
  ghost: 'border-transparent bg-transparent text-muted hover:bg-navy-800 hover:text-ink',
  danger: 'border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-sm',
}

export function buttonStyles(variant: ButtonVariant = 'primary', size: ButtonSize = 'md'): string {
  return cn(
    'inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-colors',
    'disabled:cursor-not-allowed disabled:opacity-50',
    VARIANTS[variant],
    SIZES[size],
  )
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  disabledReason?: string
  icon?: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabledReason,
  icon,
  className,
  children,
  disabled,
  title,
  ...rest
}: ButtonProps) {
  const reasonId = useId()
  const isDisabled = disabled || loading
  const button = (
    <button
      {...rest}
      type={rest.type ?? 'button'}
      className={cn(buttonStyles(variant, size), className)}
      disabled={isDisabled}
      title={disabledReason ?? title}
      aria-describedby={disabledReason ? reasonId : undefined}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  )

  if (!disabledReason) return button

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <span id={reasonId} className="sr-only">
        {disabledReason}
      </span>
      <span className="inline-flex" title={disabledReason}>
        {button}
      </span>
    </span>
  )
}
