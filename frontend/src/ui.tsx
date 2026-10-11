import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { setLang, t, useLang } from './i18n'
import { api, GRADE_TITLES, SPEC_TITLES } from './api'

export function ErrorBox({ error }: { error?: string }) {
  return error ? <div className="alert error" role="alert">{error}</div> : null
}

/** Загрузка данных с повторным запросом по reload(). */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const reload = useCallback(() => {
    if (!path) return
    setLoading(true)
    api<T>(path)
      .then((d) => {
        setData(d)
        setError('')
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [path])
  useEffect(reload, [reload])
  return { data, error, loading, reload, setData }
}

export function Category({ spec, grade, confirmed = true }: { spec?: string | null; grade?: string | null; confirmed?: boolean }) {
  if (!spec || !grade) return <span className="badge warn">Категория не присвоена</span>
  return (
    <span className={`badge ${confirmed ? '' : 'warn'}`} title={confirmed ? 'Грейд подтверждён тестом' : 'Грейд заявлен, но тестом не подтверждён'}>
      {SPEC_TITLES[spec] ?? spec} · {GRADE_TITLES[grade] ?? grade}{!confirmed && ' · не подтверждён'}
    </span>
  )
}

export function SkillChips({ verified, declared }: { verified: Record<string, number>; declared?: string[] }) {
  const v = Object.entries(verified ?? {}).sort((a, b) => b[1] - a[1])
  const onlyDeclared = (declared ?? []).filter((d) => !(d in (verified ?? {})))
  return (
    <div className="chips">
      {v.map(([k, s]) => (
        <span key={k} className={`badge ${s >= 0.6 ? 'ok' : s >= 0.4 ? '' : 'warn'}`} title="Подтверждено тестом">
          ✓ {k} {Math.round(s * 100)}%
        </span>
      ))}
      {onlyDeclared.map((d) => (
        <span key={d} className="badge neutral" title="Только заявлено в резюме">{d}</span>
      ))}
    </div>
  )
}

export function StatusBadge({ status, titles }: { status: string; titles: Record<string, string> }) {
  const cls = status === 'accepted' || status === 'invited' || status === 'offer' || status === 'hired' ? 'ok' : status === 'declined' || status === 'rejected' || status === 'expired' ? 'bad' : status === 'sent' ? 'live' : ''
  return <span className={`badge ${cls}`}>{titles[status] ?? status}</span>
}

/* ---------------------------------------------------------------- иконки (Lucide-стиль, inline SVG) */
const PATHS: Record<string, string> = {
  terminal: 'M4 17l6-6-6-6M12 19h8',
  star: 'M12 2l3 6.5 7 1-5 4.8 1.2 7L12 18l-6.2 3.3L7 14.3 2 9.5l7-1z',
  mail: 'M4 4h16v16H4zM4 7l8 6 8-6',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  lock: 'M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4',
  chat: 'M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z',
  check: 'M20 6L9 17l-5-5',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  key: 'M15 7a4 4 0 1 1-3.5 6L4 20.5V17h3v-3h3l1.5-1.5A4 4 0 0 1 15 7z',
  trophy: 'M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3',
  zap: 'M13 2L3 14h9l-1 8 10-12h-9z',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v7H2v-7z',
  task: 'M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9',
  x: 'M18 6L6 18M6 6l12 12',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4z',
  link: 'M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1',
  flag: 'M4 22V4M4 4h12l-2 4 2 4H4',
  globe: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20',
  briefcase: 'M3 7h18v13H3zM8 7V4h8v3M3 13h18',
  user: 'M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z',
}

export function Icon({ name, className }: { name: keyof typeof PATHS | string; className?: string }) {
  return (
    <svg className={className} width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? ''} />
    </svg>
  )
}

/** Знак: узлы, соединённые линиями (графический мотив брендбука ФСП). */
export function LogoMark({ className = 'mark' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 34 34" aria-hidden="true">
      <rect width="34" height="34" rx="9" fill="#402fff" />
      <path d="M9 23 L16 11 L25 15 L21 25 Z M16 11 L21 25" stroke="#fff" strokeOpacity=".55" strokeWidth="1.4" fill="none" />
      <circle cx="9" cy="23" r="2.6" fill="#fff" />
      <circle cx="16" cy="11" r="2.6" fill="#fff" />
      <circle cx="21" cy="25" r="2.6" fill="#fff" />
      <circle cx="25" cy="15" r="3" fill="#ec1d35" />
    </svg>
  )
}

// Узлы «сети регионов»: вытянутое облако с запада на восток, как карта представительств ФСП
const NODES: [number, number, string?][] = [
  [40, 210], [90, 150, 'b'], [120, 250], [170, 120], [190, 200, 'r'], [240, 280], [260, 160], [300, 90, 'b'],
  [320, 230], [370, 140], [400, 300], [420, 200, 'b'], [470, 110], [500, 250], [540, 170, 'r'], [580, 80],
  [600, 230], [640, 140, 'b'], [680, 290], [700, 190],
]
const EDGES = [
  [0, 1], [0, 2], [1, 3], [1, 4], [2, 4], [2, 5], [3, 6], [3, 7], [4, 6], [4, 8], [5, 8], [6, 7], [6, 9], [7, 12], [8, 10],
  [8, 11], [9, 11], [9, 12], [10, 13], [11, 13], [11, 14], [12, 14], [12, 15], [13, 16], [14, 16], [14, 17], [15, 17],
  [16, 18], [16, 19], [17, 19], [18, 19],
]

export function Network({ className = '' }: { className?: string }) {
  return (
    <svg className={`network ${className}`} viewBox="0 0 740 380" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      {EDGES.map(([a, b], i) => (
        <line key={i} className="edge" x1={NODES[a][0]} y1={NODES[a][1]} x2={NODES[b][0]} y2={NODES[b][1]} />
      ))}
      {NODES.map(([x, y, t], i) => (
        <g key={i}>
          {t && <circle className="halo" cx={x} cy={y} r={9} style={{ animationDelay: `${(i % 5) * 0.6}s` }} />}
          <circle className={`node ${t ?? ''}`} cx={x} cy={y} r={t ? 5 : 3} style={{ animationDelay: `${(i % 7) * 0.5}s` }} />
        </g>
      ))}
    </svg>
  )
}

/* ---------------------------------------------------------------- тема */
type Theme = 'light' | 'dark'
const THEME_KEY = 'fsp_theme'
const themeListeners = new Set<() => void>()

function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(THEME_KEY)
    return t === 'light' || t === 'dark' ? t : null
  } catch {
    return null
  }
}
function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
export function currentTheme(): Theme {
  return (document.documentElement.dataset.theme as Theme) || storedTheme() || systemTheme()
}
export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', t === 'dark' ? '#0d0e12' : '#1b1c21')
  themeListeners.forEach((l) => l())
}
export function initTheme() {
  applyTheme(storedTheme() ?? systemTheme())
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!storedTheme()) applyTheme(e.matches ? 'dark' : 'light')
  })
}
export function useTheme(): Theme {
  return useSyncExternalStore((cb) => { themeListeners.add(cb); return () => themeListeners.delete(cb) }, currentTheme)
}

export function ThemeToggle() {
  const theme = useTheme()
  const toggle = (e: React.MouseEvent) => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    const set = () => {
      applyTheme(next)
      try { localStorage.setItem(THEME_KEY, next) } catch { /* приватный режим */ }
    }
    const doc = document as Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } }
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (!doc.startViewTransition || reduce) return set()
    // Новая тема раскрывается кругом от кнопки
    document.documentElement.style.setProperty('--tx', `${e.clientX}px`)
    document.documentElement.style.setProperty('--ty', `${e.clientY}px`)
    document.documentElement.classList.add('theme-switch')
    doc.startViewTransition(set).finished.finally(() => document.documentElement.classList.remove('theme-switch'))
  }
  return (
    <button className="icon-btn" onClick={toggle} aria-label={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'} title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}>
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
    </button>
  )
}

/* ---------------------------------------------------------------- тосты */
type ToastItem = { id: number; text: string; kind: 'ok' | 'error'; out?: boolean }
let toasts: ToastItem[] = []
const toastListeners = new Set<() => void>()
const emit = () => toastListeners.forEach((l) => l())

export function toast(text: string, kind: 'ok' | 'error' = 'ok') {
  const id = Date.now() + Math.random()
  toasts = [...toasts, { id, text, kind }]
  emit()
  setTimeout(() => { toasts = toasts.map((t) => (t.id === id ? { ...t, out: true } : t)); emit() }, 3200)
  setTimeout(() => { toasts = toasts.filter((t) => t.id !== id); emit() }, 3500)
}

export function Toasts() {
  const items = useSyncExternalStore((cb) => { toastListeners.add(cb); return () => toastListeners.delete(cb) }, () => toasts)
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => <div key={t.id} className={`toast ${t.kind} ${t.out ? 'out' : ''}`}>{t.text}</div>)}
    </div>
  )
}

/* ---------------------------------------------------------------- скелетоны, пустые состояния */
export function Skeleton({ cards = 2 }: { cards?: number }) {
  return (
    <div className="page" aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="card">
          <div className="skeleton sk-title" />
          <div className="skeleton sk-line" style={{ width: '92%' }} />
          <div className="skeleton sk-line" style={{ width: '76%' }} />
          <div className="skeleton sk-line" style={{ width: '58%' }} />
        </div>
      ))}
    </div>
  )
}

/** Пока данных нет: ошибка или скелетон. */
export function Pending({ error, cards }: { error?: string; cards?: number }) {
  return error ? <div className="page"><ErrorBox error={error} /></div> : <Skeleton cards={cards} />
}

export function Empty({ icon = 'inbox', title, children }: { icon?: string; title: string; children?: ReactNode }) {
  return (
    <div className="card empty">
      <Icon name={icon} />
      <h3 style={{ marginBottom: 6 }}>{title}</h3>
      {children && <div className="muted small">{children}</div>}
    </div>
  )
}

/* ---------------------------------------------------------------- движение */
/** «Прожектор» на карточках: координаты курсора в CSS-переменные --mx/--my. */
export function initSpotlight() {
  window.addEventListener('pointermove', (e) => {
    const el = (e.target as HTMLElement | null)?.closest?.('.card.spot, a.card') as HTMLElement | null
    if (!el) return
    const r = el.getBoundingClientRect()
    el.style.setProperty('--mx', `${e.clientX - r.left}px`)
    el.style.setProperty('--my', `${e.clientY - r.top}px`)
  }, { passive: true })
}

/** Появление элементов [data-reveal] при прокрутке — для всех страниц сразу, включая подгруженные позже. */
export function initReveal() {
  if (!('IntersectionObserver' in window) || !('MutationObserver' in window)) {
    document.documentElement.classList.add('no-reveal')
    return
  }
  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target) }
  }), { threshold: 0.08, rootMargin: '0px 0px -40px 0px' })
  const scan = () => document.querySelectorAll('[data-reveal]:not([data-seen])').forEach((el) => {
    el.setAttribute('data-seen', '')
    io.observe(el)
  })
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true })
  scan()
}

/** Число, которое «набегает» до значения. */
export function CountUp({ to, duration = 1200, suffix = '' }: { to: number; duration?: number; suffix?: string }) {
  const [v, setV] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setV(to); return }
    let raf = 0
    let start = 0
    const tick = (t: number) => {
      if (!start) start = t
      const p = Math.min(1, (t - start) / duration)
      setV(Math.round(to * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [to, duration])
  return <span ref={ref}>{v}{suffix}</span>
}

/** Кольцо процента соответствия. */
export function Ring({ percent, label = 'match', size = 104 }: { percent: number; label?: string; size?: number }) {
  const r = 44
  const c = 2 * Math.PI * r
  const [shown, setShown] = useState(0)
  useEffect(() => { const t = requestAnimationFrame(() => setShown(percent)); return () => cancelAnimationFrame(t) }, [percent])
  const tone = percent >= 70 ? 'ok' : percent >= 45 ? '' : percent >= 25 ? 'warn' : 'bad'
  return (
    <div className="ring" style={{ width: size, height: size }} role="img" aria-label={`Соответствие ${percent}%`}>
      <svg viewBox="0 0 100 100">
        <circle className="track" cx="50" cy="50" r={r} fill="none" strokeWidth="8" />
        <circle className={`val ${tone}`} cx="50" cy="50" r={r} fill="none" strokeWidth="8"
                strokeDasharray={c} strokeDashoffset={c * (1 - shown / 100)} />
      </svg>
      <div className="num"><CountUp to={percent} suffix="%" duration={1000} /><small>{label}</small></div>
    </div>
  )
}

/* ---------------------------------------------------------------- переписка */
export function Chat({ base, me, disabled }: { base: string; me: 'candidate' | 'employer'; disabled?: boolean }) {
  const msgs = useApi<any[]>(`${base}/messages`)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const log = useRef<HTMLDivElement>(null)
  const { reload } = msgs
  useEffect(() => {
    const t = setInterval(reload, 5000)
    return () => clearInterval(t)
  }, [reload])
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }) }, [msgs.data?.length])
  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    try {
      await api(`${base}/messages`, { body: { text } })
      setText('')
      reload()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }
  const fmt = (s: string) => new Date(s + (s.endsWith('Z') ? '' : 'Z')).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  return (
    <div className="chat">
      <div className="row between small"><strong className="mono">// переписка</strong><span className="muted">контакты не раскрываются</span></div>
      <div className="chat-log" ref={log}>
        {!msgs.data?.length && <div className="chat-empty">Сообщений пока нет — задайте вопрос о вакансии или условиях.</div>}
        {msgs.data?.map((m) => (
          <div key={m.id} className={`bubble ${m.sender === me ? 'me' : 'them'}`}>
            {m.text}
            <time>{fmt(m.created_at)}{m.sender === me && m.read_at ? ' · прочитано' : ''}</time>
          </div>
        ))}
      </div>
      {!disabled && (
        <form className="chat-form" onSubmit={send}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Сообщение…" maxLength={4000} aria-label="Сообщение" />
          <button disabled={busy || !text.trim()} aria-label="Отправить"><Icon name="send" className="" /></button>
        </form>
      )}
    </div>
  )
}

/** Вилка зарплаты всегда подписана: суммы до вычета НДФЛ (gross). */
export function Salary({ from, to, big }: { from: number; to: number; big?: boolean }) {
  return (
    <span className="price" style={big ? { fontSize: 22 } : undefined}>
      {from.toLocaleString('ru-RU')} – {to.toLocaleString('ru-RU')} ₽<small title="Суммы до вычета НДФЛ">gross, до НДФЛ</small>
    </span>
  )
}


/**
 * Фон приложения: контрастная графитовая сетка (миллиметровка) с живыми эффектами —
 * подсветка сетки вокруг курсора, сканирующий луч, медленный дрейф и вспышки узлов.
 * Декоративный слой: под контентом, без событий мыши, скрыт от скринридеров.
 */
const SPARKS = [[3, 4], [9, 2], [14, 6], [6, 9], [11, 11], [17, 3], [2, 13], [15, 14], [8, 16], [19, 9]]

export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="bd-grid" />
      <div className="bd-glow" />
      <div className="bd-scan" />
      {SPARKS.map(([x, y], i) => (
        <span key={i} className="bd-spark" style={{ left: `${x * 120}px`, top: `${y * 120}px`, animationDelay: `${(i * 1.7) % 9}s` }} />
      ))}
    </div>
  )
}

/**
 * Микровзаимодействия (по рекомендациям ui-ux-pro-max): волна от точки нажатия, наклон карточек
 * за курсором, «магнит» только на главных кнопках (.btn.lg / button.lg) с ограничением силы,
 * подсветка сетки и полоса прогресса прокрутки. При prefers-reduced-motion всё отключено.
 */
export function initMotion() {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')
  const off = () => !!reduce?.matches
  const root = document.documentElement

  // Подсветка сетки и наклон карточек — один обработчик, обновления раз в кадр
  let raf = 0
  let last: PointerEvent | null = null
  let tilted: HTMLElement | null = null
  const resetTilt = () => { if (tilted) { tilted.style.transform = ''; tilted = null } }
  window.addEventListener('pointermove', (e) => {
    last = e
    if (raf || off()) return
    raf = requestAnimationFrame(() => {
      raf = 0
      if (!last) return
      root.style.setProperty('--gx', `${last.clientX}px`)
      root.style.setProperty('--gy', `${last.clientY}px`)
      const card = (last.target as HTMLElement | null)?.closest?.('.card.lift, a.card') as HTMLElement | null
      if (card !== tilted) resetTilt()
      if (card && last.pointerType === 'mouse') {
        const r = card.getBoundingClientRect()
        const px = (last.clientX - r.left) / r.width - 0.5
        const py = (last.clientY - r.top) / r.height - 0.5
        card.style.transform = `perspective(900px) rotateX(${(-py * 4).toFixed(2)}deg) rotateY(${(px * 5).toFixed(2)}deg) translateY(-3px)`
        tilted = card
      }
    })
  }, { passive: true })
  document.addEventListener('pointerleave', resetTilt)

  // Волна от точки нажатия на кнопках
  document.addEventListener('pointerdown', (e) => {
    if (off()) return
    const btn = (e.target as HTMLElement | null)?.closest?.('button, .btn') as HTMLElement | null
    if (!btn || (btn as HTMLButtonElement).disabled) return
    const r = btn.getBoundingClientRect()
    const size = Math.max(r.width, r.height) * 2
    const s = document.createElement('span')
    s.className = 'ripple'
    s.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - r.left - size / 2}px;top:${e.clientY - r.top - size / 2}px`
    btn.appendChild(s)
    s.addEventListener('animationend', () => s.remove())
  })

  // «Магнит» для главных кнопок: сила ограничена 0.25, элемент не покидает свою зону нажатия
  document.addEventListener('pointermove', (e) => {
    if (off() || e.pointerType !== 'mouse') return
    const el = (e.target as HTMLElement | null)?.closest?.('.btn.lg, button.lg') as HTMLElement | null
    document.querySelectorAll<HTMLElement>('.magnet-on').forEach((m) => { if (m !== el) { m.style.translate = ''; m.classList.remove('magnet-on') } })
    if (!el) return
    const r = el.getBoundingClientRect()
    el.classList.add('magnet-on')
    el.style.translate = `${((e.clientX - r.left - r.width / 2) * 0.25).toFixed(1)}px ${((e.clientY - r.top - r.height / 2) * 0.25).toFixed(1)}px`
  }, { passive: true })

  // Прогресс прокрутки страницы
  const onScroll = () => {
    const max = root.scrollHeight - root.clientHeight
    root.style.setProperty('--scroll', max > 0 ? String(Math.min(1, window.scrollY / max)) : '0')
  }
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
  onScroll()
}


/* ---------------------------------------------------------------- наполнение страниц */
/** Шапка страницы: надзаголовок, заголовок, пояснение и место для действий справа. */
export function PageHead({ kicker, title, children, aside }: { kicker: string; title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="ph-main">
        <span className="kicker">{t(kicker)}</span>
        <h1><span className="ph-mark">{t(title)}</span></h1>
        {children && <p className="ph-sub">{children}</p>}
      </div>
      {aside && <div className="ph-aside">{aside}</div>}
    </header>
  )
}

/** KPI-плитка: число, подпись, мелкое пояснение. */
export function Kpi({ value, label, hint, icon, color = 'var(--brand)', suffix = '' }: {
  value: number | null | undefined; label: string; hint?: string; icon: string; color?: string; suffix?: string
}) {
  return (
    <div className="kpi card spot lift" style={{ '--c': color } as React.CSSProperties}>
      <span className="kpi-icon"><Icon name={icon} /></span>
      <b>{value == null ? '—' : <CountUp to={value} suffix={suffix} duration={900} />}</b>
      <span className="kpi-label">{label}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  )
}

/** Боковая карточка с подсказками. */
export function Tips({ title, items }: { title: string; items: [string, string][] }) {
  return (
    <aside className="card tips">
      <h3>{t(title)}</h3>
      <ol>
        {items.map(([t, d]) => <li key={t}><strong>{t}</strong><span>{d}</span></li>)}
      </ol>
    </aside>
  )
}

/** Переключатель языка интерфейса RU / EN. */
export function LangToggle() {
  const l = useLang()
  return (
    <button className="icon-btn lang-btn" onClick={() => setLang(l === 'ru' ? 'en' : 'ru')}
            aria-label={l === 'ru' ? 'Switch to English' : 'Переключить на русский'} title={l === 'ru' ? 'English' : 'Русский'}>
      {l === 'ru' ? 'EN' : 'RU'}
    </button>
  )
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="sf-inner">
        <div className="sf-brand">
          <span className="logo" style={{ color: 'var(--text)' }}><LogoMark /><span>ФСП<span className="sub"> / карьера</span></span></span>
          <p className="small muted">Платформа подбора ИТ-специалистов с верифицированным профилем достижений участников
            Федерации спортивного программирования. Работодатель находит категорию и приглашает сам.</p>
        </div>
        <div className="sf-col">
          <span className="sf-title">{t('Механика')}</span>
          <span>Адаптивный тест IRT/CAT</span><span>Объяснимый подбор</span><span>Обратная механика найма</span>
        </div>
        <div className="sf-col">
          <span className="sf-title">{t('Доверие')}</span>
          <span>Согласия по 152-ФЗ</span><span>Вход через ФСП ID</span><span>Контакты только с согласия</span>
        </div>
        <div className="sf-col">
          <span className="sf-title">{t('Для проверки')}</span>
          <span><code>candidate@demo.ru</code></span><span><code>employer@demo.ru</code></span><span>пароль <code>demo12345</code></span>
        </div>
      </div>
      <div className="sf-bottom">
        <span>© 2026 ФСП Карьера · хакатон «Лидеры цифровой трансформации»</span>
        <span className="mono">зарплаты указаны до вычета НДФЛ (gross) · API: /docs</span>
      </div>
    </footer>
  )
}
