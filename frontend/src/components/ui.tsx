/** Small shared primitives. Deliberately plain — no component library. */
import clsx from 'clsx'
import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'outline' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
}

export function Button({
  variant = 'outline', size = 'md', loading, className, children, disabled, ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap',
        'transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-9 px-3.5 text-sm',
        variant === 'primary' && 'bg-brand text-canvas hover:opacity-90',
        variant === 'outline' && 'border border-line bg-surface text-ink hover:bg-raised',
        variant === 'ghost' && 'text-ink-muted hover:bg-raised hover:text-ink',
        variant === 'danger' && 'border border-danger/40 text-danger hover:bg-danger/10',
        className,
      )}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" /> : null}
      {children}
    </button>
  )
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={clsx(
        'h-9 w-full rounded-md border border-line bg-surface px-3 text-sm text-ink',
        'placeholder:text-ink-faint focus:border-brand focus:outline-none',
        className,
      )}
    />
  )
}

export function Badge({
  children, className, title,
}: { children: ReactNode; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium leading-none',
        'border-line bg-raised text-ink-muted',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Panel({
  title, actions, children, className,
}: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx('flex flex-col rounded-lg border border-line bg-surface', className)}>
      {title ? (
        <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-line-soft px-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {actions ? <div className="flex items-center gap-1.5">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  )
}

export function EmptyState({
  icon, title, hint, action,
}: { icon?: ReactNode; title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
      {icon ? <div className="text-ink-faint">{icon}</div> : null}
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint ? <p className="max-w-sm text-xs text-ink-muted">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-1 items-center justify-center gap-2 p-8 text-sm text-ink-muted">
      <Loader2 className="size-4 animate-spin" />
      {label}
    </div>
  )
}

/** Keyboard shortcut hint. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line bg-raised px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
      {children}
    </kbd>
  )
}

/** Highlights every occurrence of `query` inside `text`. */
export function Highlight({ text, query }: { text: string; query: string }) {
  const needle = query.trim()
  if (!needle) return <>{text}</>
  const index = text.toLowerCase().indexOf(needle.toLowerCase())
  if (index === -1) return <>{text}</>
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-[2px] bg-brand/30 text-ink">{text.slice(index, index + needle.length)}</mark>
      <Highlight text={text.slice(index + needle.length)} query={needle} />
    </>
  )
}
