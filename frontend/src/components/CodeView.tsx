/**
 * A read-only code pane with light XML/JSON highlighting.
 *
 * Device replies are the densest thing in the app — a wall of angle brackets
 * that all look alike. Colour separates structure (tags) from the values you
 * are actually reading, which is most of what makes it legible.
 */
import clsx from 'clsx'
import { Check, Copy, WrapText } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import { Button } from './ui'

type Kind = 'xml' | 'json' | 'text'

/** Split source into styled spans. Purely presentational — never parses semantics. */
function highlightXml(source: string): ReactNode[] {
  const out: ReactNode[] = []
  // One pass: declarations/comments, then tags, then the text between them.
  const pattern = /(<\?[\s\S]*?\?>)|(<!--[\s\S]*?-->)|(<\/?[^>]+>)/g
  let last = 0
  let match: RegExpExecArray | null
  let key = 0

  const pushText = (text: string) => {
    if (text) out.push(<span key={key++} className="text-code-value">{text}</span>)
  }

  while ((match = pattern.exec(source)) !== null) {
    pushText(source.slice(last, match.index))
    last = match.index + match[0].length

    if (match[1] || match[2]) {
      out.push(<span key={key++} className="text-code-muted">{match[0]}</span>)
      continue
    }

    // A tag: colour the name, then each attribute name and quoted value.
    const tag = match[0]
    const inner = /^<\/?([^\s/>]+)([\s\S]*?)\/?>$/.exec(tag)
    if (!inner) {
      out.push(<span key={key++} className="text-code-tag">{tag}</span>)
      continue
    }
    const [, name, rest] = inner
    const open = tag.startsWith('</') ? '</' : '<'
    const close = tag.endsWith('/>') ? '/>' : '>'

    out.push(<span key={key++} className="text-code-punct">{open}</span>)
    out.push(<span key={key++} className="text-code-tag">{name}</span>)

    const attr = /([\w:.-]+)(\s*=\s*)("[^"]*"|'[^']*')/g
    let attrLast = 0
    let a: RegExpExecArray | null
    while ((a = attr.exec(rest)) !== null) {
      out.push(<span key={key++} className="text-code-punct">{rest.slice(attrLast, a.index)}</span>)
      out.push(<span key={key++} className="text-code-attr">{a[1]}</span>)
      out.push(<span key={key++} className="text-code-punct">{a[2]}</span>)
      out.push(<span key={key++} className="text-code-string">{a[3]}</span>)
      attrLast = a.index + a[0].length
    }
    out.push(<span key={key++} className="text-code-punct">{rest.slice(attrLast)}</span>)
    out.push(<span key={key++} className="text-code-punct">{close}</span>)
  }
  pushText(source.slice(last))
  return out
}

function highlightJson(source: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /("(?:\\.|[^"\\])*")(\s*:)?|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = pattern.exec(source)) !== null) {
    if (m.index > last) {
      out.push(<span key={key++} className="text-code-punct">{source.slice(last, m.index)}</span>)
    }
    last = m.index + m[0].length
    if (m[1] && m[2]) {
      out.push(<span key={key++} className="text-code-attr">{m[1]}</span>)
      out.push(<span key={key++} className="text-code-punct">{m[2]}</span>)
    } else if (m[1]) {
      out.push(<span key={key++} className="text-code-string">{m[1]}</span>)
    } else if (m[3]) {
      out.push(<span key={key++} className="text-code-number">{m[3]}</span>)
    } else {
      out.push(<span key={key++} className="text-code-tag">{m[4]}</span>)
    }
  }
  out.push(<span key={key++} className="text-code-punct">{source.slice(last)}</span>)
  return out
}

export function CodeView({
  source, kind = 'xml', empty, actions,
}: {
  source: string
  kind?: Kind
  empty?: ReactNode
  actions?: ReactNode
}) {
  const [copied, setCopied] = useState(false)
  const [wrap, setWrap] = useState(false)

  const painted = useMemo(() => {
    if (!source) return null
    if (kind === 'xml') return highlightXml(source)
    if (kind === 'json') return highlightJson(source)
    return source
  }, [source, kind])

  const lineCount = useMemo(() => (source ? source.split('\n').length : 0), [source])

  if (!source) {
    return <div className="flex min-h-0 flex-1 items-center justify-center p-4">{empty}</div>
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-1.5 px-2 py-1">
        {actions}
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-ink-faint">
          {lineCount} line{lineCount === 1 ? '' : 's'}
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setWrap((w) => !w)}
          title={wrap ? 'Stop wrapping long lines' : 'Wrap long lines'}
          className={wrap ? 'text-brand' : undefined}
        >
          <WrapText className="size-3" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          title="Copy"
          onClick={() => {
            void navigator.clipboard?.writeText(source)
            setCopied(true)
            setTimeout(() => setCopied(false), 1200)
          }}
        >
          {copied ? <Check className="size-3 text-ok" /> : <Copy className="size-3" />}
        </Button>
      </div>
      <pre
        className={clsx(
          'min-h-0 flex-1 overflow-auto bg-canvas/50 px-3 pb-3 font-mono text-[11.5px] leading-[1.65]',
          wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre',
        )}
      >
        {painted}
      </pre>
    </div>
  )
}
