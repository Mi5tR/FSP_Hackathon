import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api, GRADE_ORDER, GRADE_TITLES, session, type Role } from './api'
import { t, useLang } from './i18n'
import CandidateHome from './pages/candidate/Home'
import CandidateProfile from './pages/candidate/Profile'
import Survey from './pages/candidate/Survey'
import TestRun from './pages/candidate/TestRun'
import CandidateInvitations from './pages/candidate/Invitations'
import Vacancies from './pages/candidate/Vacancies'
import Settings from './pages/candidate/Settings'
import EmployerHome from './pages/employer/Home'
import NeedPage from './pages/employer/NeedPage'
import EmployerInvitations from './pages/employer/Invitations'
import Company from './pages/employer/Company'
import Search from './pages/employer/Search'
import Tasks from './pages/employer/Tasks'
import { FspCallback, FspIdButton, FspIdLogin } from './fspid'
import { Backdrop, CountUp, ErrorBox, Footer, Icon, Kpi, LangToggle, LogoMark, Network, ThemeToggle, toast, Toasts, useApi } from './ui'

/** Счётчики разделов меню: приглашения и сообщения, новые задания, новые кандидаты в категориях. */
function useBadges(role: Role | null, path: string) {
  const [b, setB] = useState<Record<string, number>>({})
  useEffect(() => {
    if (!role) return
    const url = role === 'candidate' ? '/candidate/badges' : '/employer/badges'
    const load = () => api<Record<string, number>>(url).then(setB).catch(() => setB({}))
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [role, path])
  return b
}

type NavItem = { to: string; title: string; hint: string; icon: string; color: string; end?: boolean; badge?: string }

// Разделы кабинетов: один источник для шапки и шторки. Цвета — бренд ФСП и производные от него
const NAV: Record<Role, NavItem[]> = {
  candidate: [
    { to: '/c', end: true, title: 'Мой путь', hint: 'шаги, категория, история теста', icon: 'zap', color: '#402fff' },
    { to: '/c/invitations', title: 'Приглашения', hint: 'предложения и переписка', icon: 'mail', color: '#ec1d35', badge: 'invitations' },
    { to: '/c/vacancies', title: 'Вакансии и задания', hint: 'отклики и короткие задачи', icon: 'task', color: '#0ea5a4', badge: 'tasks' },
    { to: '/c/profile', title: 'Профиль', hint: 'резюме, стек, PDF-профиль', icon: 'user', color: '#f59e0b' },
    { to: '/c/settings', title: 'Приватность и ФСП', hint: 'согласия, ФСП ID', icon: 'shield', color: '#8b5cf6' },
  ],
  employer: [
    { to: '/e', end: true, title: 'Потребности', hint: 'кого ищем, новые кандидаты', icon: 'star', color: '#402fff', badge: 'needs' },
    { to: '/e/search', title: 'Банк кандидатов', hint: 'поиск по категориям', icon: 'eye', color: '#0ea5a4' },
    { to: '/e/invitations', title: 'Приглашения', hint: 'статусы и переписка', icon: 'mail', color: '#ec1d35', badge: 'invitations' },
    { to: '/e/tasks', title: 'Задания', hint: 'регулярные задачи и оценки', icon: 'task', color: '#f59e0b' },
    { to: '/e/company', title: 'Компания', hint: 'доверие и ATS Huntflow', icon: 'inbox', color: '#8b5cf6' },
  ],
}

const GUEST_NAV: NavItem[] = [
  { to: '/', end: true, title: 'О платформе', hint: 'как это работает', icon: 'star', color: '#402fff' },
  { to: '/login', title: 'Вход', hint: 'email, ФСП ID или демо', icon: 'key', color: '#0ea5a4' },
  { to: '/register?role=candidate', title: 'Я ищу работу', hint: 'регистрация соискателя', icon: 'user', color: '#f59e0b' },
  { to: '/register?role=employer', title: 'Я ищу специалистов', hint: 'регистрация работодателя', icon: 'inbox', color: '#ec1d35' },
]

function Drawer({ open, onClose, items, badges, role, onLogout }: {
  open: boolean; onClose: () => void; items: NavItem[]; badges: Record<string, number>; role: Role | null; onLogout: () => void
}) {
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    panel.current?.querySelector<HTMLElement>('a, button')?.focus()
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [open, onClose])
  return (
    <div className={`drawer-root ${open ? 'open' : ''}`} aria-hidden={!open}>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" ref={panel} role="dialog" aria-modal="true" aria-label="Меню разделов">
        <div className="drawer-head">
          <span className="orb a" />
          <div className="row between" style={{ flexWrap: 'nowrap' }}>
            <span className="logo" style={{ margin: 0 }}><LogoMark /><span>ФСП<span className="sub"> / карьера</span></span></span>
            <button className="icon-btn" onClick={onClose} aria-label="Закрыть меню" tabIndex={open ? 0 : -1}><Icon name="x" /></button>
          </div>
          <div className="drawer-who">
            <span className="avatar"><Icon name={role === 'employer' ? 'inbox' : 'user'} /></span>
            <div>
              <strong>{role === 'candidate' ? 'Соискатель' : role === 'employer' ? 'Работодатель' : 'Гость'}</strong>
              <div className="small">{role ? 'личный кабинет' : 'войдите или зарегистрируйтесь'}</div>
            </div>
          </div>
        </div>
        <nav className="drawer-nav" aria-label="Разделы">
          {items.map((it, i) => (
            <NavLink key={it.to} to={it.to} end={it.end} onClick={onClose} viewTransition tabIndex={open ? 0 : -1}
                     style={{ '--c': it.color, '--i': i } as React.CSSProperties}>
              <span className="tile"><Icon name={it.icon} /></span>
              <span className="txt"><b>{t(it.title)}</b><small>{t(it.hint)}</small></span>
              {it.badge && (badges[it.badge] ?? 0) > 0 && <span className="nav-dot">{badges[it.badge]}</span>}
              <span className="chev">›</span>
            </NavLink>
          ))}
        </nav>
        <div className="drawer-foot">
          <div className="row between" style={{ flexWrap: 'nowrap' }}>
            <span className="small">Тема оформления</span>
            <ThemeToggle />
          </div>
          {role
            ? <button className="danger" style={{ width: '100%' }} onClick={() => { onClose(); onLogout() }} tabIndex={open ? 0 : -1}>Выйти из аккаунта</button>
            : <div className="small muted mono">demo: пароль demo12345</div>}
        </div>
      </aside>
    </div>
  )
}

function TopBar() {
  const nav = useNavigate()
  const loc = useLocation()
  const role = session.role
  const badges = useBadges(role, loc.pathname)
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])
  const items = role ? NAV[role] : GUEST_NAV
  const logout = () => {
    session.clear()
    toast('Вы вышли из аккаунта')
    nav('/', { viewTransition: true })
  }
  return (
    <>
      <header className="topbar">
        <button className="icon-btn burger" onClick={() => setOpen(true)} aria-label="Открыть меню разделов" aria-expanded={open}>
          <span /><span /><span />
        </button>
        <NavLink to="/" className="logo" aria-label="ФСП Карьера, на главную" viewTransition>
          <LogoMark />
          <span>ФСП<span className="sub"> / карьера</span></span>
        </NavLink>
        {role && (
          <nav aria-label="Основная навигация">
            {NAV[role].map((it) => (
              <NavLink key={it.to} to={it.to} end={it.end} viewTransition style={{ '--c': it.color } as React.CSSProperties}>
                <span className="dot-c" />{t(it.title)}
                {it.badge && (badges[it.badge] ?? 0) > 0 && <span className="nav-dot" aria-label={`новых: ${badges[it.badge]}`}>{badges[it.badge]}</span>}
              </NavLink>
            ))}
          </nav>
        )}
        <span className="spacer" />
        {role && <span className="who">{t(role === 'candidate' ? 'соискатель' : 'работодатель')}</span>}
        <LangToggle />
        <ThemeToggle />
        {role ? (
          <button className="ghost" onClick={logout}>{t('Выйти')}</button>
        ) : (
          <NavLink to="/login" className="btn ghost" viewTransition>{t('Войти')}</NavLink>
        )}
      </header>
      <Drawer open={open} onClose={close} items={items} badges={badges} role={role} onLogout={logout} />
    </>
  )
}

function Guard({ role, children }: { role: Role; children: ReactNode }) {
  if (!session.token) return <Navigate to="/login" replace />
  if (session.role !== role) return <Navigate to={session.role === 'candidate' ? '/c' : '/e'} replace />
  return <>{children}</>
}

const FEATURES = [
  { title: 'Опрос и тест', icon: 'terminal',
    text: 'Вы сами выбираете грейд, адаптивный тест его подтверждает. Задания генерируются заново для каждого: ответы не «утекают», сложность выровнена.' },
  { title: 'Категория', icon: 'star',
    text: 'Например, «Backend · Middle». Грейд даёт только тест. Достижения ФСП поднимают вас внутри категории, но не меняют грейд.' },
  { title: 'Приглашение', icon: 'mail',
    text: 'Работодатель пишет первым: позиция, вилка до вычета НДФЛ, способ связи. Можно переписываться, контакты открываются только после вашего согласия.' },
]

const TRUST = [
  { icon: 'shield', title: '152-ФЗ', text: 'Согласие на обработку ПДн, обезличенные карточки, отзыв доступа к контактам в один клик.' },
  { icon: 'key', title: 'Вход через ФСП ID', text: 'Достижения подтягиваются из реестра ФСП, а не вписываются вручную.' },
  { icon: 'eye', title: 'Объяснимый подбор', text: 'Работодатель видит, почему кандидат в выдаче: блоки, навыки, флаги.' },
  { icon: 'zap', title: 'Честный тест', text: 'Уникальные варианты заданий, контроль времени и сигналы честности прохождения.' },
]

const PATHS = {
  candidate: {
    title: 'Путь соискателя', color: '#402fff', icon: 'user',
    steps: [
      ['Профиль', 'Форма или PDF-резюме с автораспознаванием, вход через ФСП ID'],
      ['Опрос и грейд', 'Направление, специализация и грейд, на который вы претендуете'],
      ['Адаптивный тест', '12–22 уникальных задания до 20 минут, сложность подстраивается под ответы'],
      ['Категория', 'Например, «Backend · Middle» — её видят работодатели'],
      ['Приглашения', 'Вилка до НДФЛ, переписка, контакты только после согласия'],
    ],
  },
  employer: {
    title: 'Путь работодателя', color: '#ec1d35', icon: 'inbox',
    steps: [
      ['Потребность текстом', 'Своими словами: стек, уровень, вилка — система разберёт сама'],
      ['Категории', 'Точная и смежные категории с числом кандидатов и долей ФСП'],
      ['Объяснимая подборка', 'Процент, блоки, покрытие каждого навыка и флаги рисков'],
      ['Шорт-лист и задания', 'Отбор без потери подборки, короткие задачи с автопроверкой'],
      ['Адресное приглашение', 'Суточный лимит по уровню доверия — приглашение ценно, а не спам'],
    ],
  },
} as const

const FAQ: [string, string][] = [
  ['Влияют ли достижения ФСП на грейд?', 'Нет. Грейд присваивает только тест. Достижения поднимают кандидата внутри его категории: учитываются число стартов и результат, все соревнования равнозначны.'],
  ['Что будет, если тест не подтвердит грейд?', 'Профиль не скрывается: работодатели видят его с пометкой «не подтверждён» ниже подтверждённых кандидатов. Тест на уровень ниже доступен сразу, попытка не сгорает.'],
  ['Можно ли подсмотреть ответы у других?', 'Задания генерируются заново для каждого кандидата из параметрических шаблонов, правильный ответ не уходит в браузер, сложность выровнена по модели IRT.'],
  ['Когда работодатель увидит мои контакты?', 'Только после того, как вы примете его приглашение или откликнетесь сами. Доступ можно отозвать в любой момент.'],
  ['Зарплата указана до или после налогов?', 'Все вилки на платформе — до вычета НДФЛ (gross), это подписано рядом с каждой суммой.'],
]

function Landing() {
  const stats = useApi<any>('/stats')
  const catalog = useApi<any>('/catalog')
  if (session.token) return <Navigate to={session.role === 'candidate' ? '/c' : '/e'} replace />
  const s = stats.data
  const countFor = (spec: string) => (s?.categories ?? []).filter((c: any) => c.specialization === spec)
  return (
    <div className="page">
      <section className="ink hero">
        <span className="orb a" /><span className="orb b" />
        <Network />
        <div className="hero-body">
          <span className="eyebrow">{t('Федерация спортивного программирования')}</span>
          <h1>{t('Работодатель сам находит вас — ')}<span className="hl">{t('по подтверждённым навыкам')}</span></h1>
          <p className="lead">
            {t('Пройдите адаптивный тест по специализации и получите категорию. Работодатели видят категорию, результаты тестов и достижения ФСП и присылают приглашение сразу с вилкой зарплаты. Контакты раскрываются только после вашего согласия.')}
          </p>
          <div className="row">
            <NavLink className="btn lg light" to="/register?role=candidate" viewTransition>{t('Я ищу работу')} <span className="arrow">→</span></NavLink>
            <NavLink className="btn lg outline-light" to="/register?role=employer" viewTransition>{t('Я ищу специалистов')}</NavLink>
          </div>
          <div className="stats">
            <div className="stat"><b><CountUp to={12} />–<CountUp to={22} /></b><span>{t('адаптивных заданий')}</span></div>
            <div className="stat"><b><CountUp to={8} /></b><span>{t('специализаций')}</span></div>
            <div className="stat"><b><CountUp to={0} /> ₽</b><span>{t('для соискателя')}</span></div>
          </div>
        </div>
      </section>

      <div className="kpis stagger">
        <Kpi value={s?.candidates} label={t('кандидатов в банке')} hint={t('с присвоенной категорией')} icon="user" color="#402fff" />
        <Kpi value={s?.with_fsp} label={t('участников ФСП')} hint={s ? `${s.achievements} результатов соревнований` : 'из реестра через ФСП ID'} icon="trophy" color="#ec1d35" />
        <Kpi value={s?.vacancies} label={t('открытых вакансий')} hint={s ? `от ${s.companies} компаний` : 'от работодателей платформы'} icon="inbox" color="#0ea5a4" />
        <Kpi value={s?.item_families} label={t('семейств заданий')} hint={t('каждый вариант генерируется заново')} icon="terminal" color="#f59e0b" />
      </div>

      <div className="section-title" data-reveal>
        <h2>{t('Как это работает')}</h2>
        <span className="muted small">{t('обратная механика: не вы рассылаете резюме, а вас приглашают')}</span>
      </div>
      <div className="grid stagger">
        {FEATURES.map((f, i) => (
          <div className="card feature spot lift" key={f.title}>
            <span className="idx">0{i + 1}</span>
            <div className="num"><Icon name={f.icon} /></div>
            <h3>{t(f.title)}</h3>
            <p className="muted small">{t(f.text)}</p>
          </div>
        ))}
      </div>

      <div className="paths" data-reveal>
        {(['candidate', 'employer'] as const).map((k) => {
          const p = PATHS[k]
          return (
            <div key={k} className="card path spot" style={{ '--c': p.color } as React.CSSProperties}>
              <div className="row between">
                <h3 className="row" style={{ gap: 10, margin: 0 }}><span className="kpi-icon"><Icon name={p.icon} /></span>{t(p.title)}</h3>
                <NavLink to={`/register?role=${k}`} className="small" viewTransition>{t('начать →')}</NavLink>
              </div>
              <ol className="timeline">
                {p.steps.map(([t, d], i) => (
                  <li key={t}><span className="tl-num">{String(i + 1).padStart(2, '0')}</span><div><strong>{t}</strong><span>{d}</span></div></li>
                ))}
              </ol>
            </div>
          )
        })}
      </div>

      <div className="section-title" data-reveal>
        <h2>{t('Специализации')}</h2>
        <span className="muted small">{t('тест проверяет ключевые навыки каждой специализации')}</span>
      </div>
      <div className="specs" data-reveal>
        {(catalog.data?.specializations ?? []).map((sp: any) => {
          const cats = countFor(sp.code)
          const total = cats.reduce((a: number, c: any) => a + c.count, 0)
          const peak = Math.max(1, ...cats.map((c: any) => c.count))
          return (
            <div key={sp.code} className="card spec spot lift">
              <div className="row between"><strong>{sp.title}</strong><span className="badge neutral">{total} канд.</span></div>
              <div className="spec-bars" aria-label="Распределение по грейдам">
                {GRADE_ORDER.map((g) => {
                  const n = cats.find((c: any) => c.grade === g)?.count ?? 0
                  return (
                    <div key={g} className="sb" title={`${GRADE_TITLES[g]}: ${n}`}>
                      <span style={{ height: `${total ? Math.max(6, (n / peak) * 100) : 6}%` }} />
                      <small>{GRADE_TITLES[g].replace('Junior', 'J').replace('Middle', 'M').replace('Senior', 'S').replace('Intern', 'I')}</small>
                    </div>
                  )
                })}
              </div>
              <div className="chips">{sp.skills.slice(0, 6).map((sk: string) => <span key={sk} className="badge neutral">{sk}</span>)}</div>
            </div>
          )
        })}
      </div>

      <div className="section-title" data-reveal><h2>{t('Почему этому можно доверять')}</h2><span className="muted small">{t('механика, а не обещания')}</span></div>
      <div className="trust" data-reveal>
        {TRUST.map((t) => (
          <div className="item" key={t.title}>
            <Icon name={t.icon} />
            <div><strong>{t.title}</strong><div className="small muted">{t.text}</div></div>
          </div>
        ))}
      </div>

      <div className="section-title" data-reveal><h2>Частые вопросы</h2><span className="muted small">коротко о главном</span></div>
      <div className="faq" data-reveal>
        {FAQ.map(([q, a]) => (
          <details key={q} className="card">
            <summary>{q}<span className="faq-plus">+</span></summary>
            <p className="small muted">{a}</p>
          </details>
        ))}
      </div>

      <section className="ink cta" data-reveal>
        <span className="orb a" />
        <div>
          <span className="eyebrow">готовы начать?</span>
          <h2>Пройдите тест один раз — дальше работодатели пишут сами</h2>
          <p className="muted">Или войдите демо-аккаунтом и посмотрите обе стороны платформы за пару минут.</p>
        </div>
        <div className="row">
          <NavLink className="btn lg light" to="/register?role=candidate" viewTransition>Создать профиль <span className="arrow">→</span></NavLink>
          <NavLink className="btn lg outline-light" to="/login" viewTransition>Демо-вход</NavLink>
        </div>
      </section>
    </div>
  )
}

function AuthSide({ title, text }: { title: string; text: string }) {
  return (
    <div className="ink auth-side">
      <span className="orb a" />
      <Network />
      <div>
        <span className="eyebrow">ФСП · Карьера</span>
        <h2 key={title} style={{ animation: 'rise .5s var(--ease-out) both' }}>{title}</h2>
        <p className="muted">{text}</p>
      </div>
      <p className="small muted mono">// подтверждённые навыки → категория → приглашение</p>
    </div>
  )
}

function QuickLogin() {
  const nav = useNavigate()
  const [busy, setBusy] = useState('')
  const go = async (role: Role) => {
    setBusy(role)
    try {
      const r = await api('/auth/demo', { body: { role } })
      session.set(r.access_token, r.role)
      toast(role === 'candidate' ? 'Создан чистый аккаунт соискателя' : 'Создан аккаунт работодателя')
      nav(role === 'candidate' ? '/c' : '/e', { viewTransition: true })
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setBusy('')
    }
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="divider">быстрый вход для проверки</div>
      <div className="quick">
        <button type="button" className="secondary" onClick={() => go('candidate')} disabled={!!busy}>
          {busy === 'candidate' ? <span className="spinner" /> : <Icon name="user" />} Соискатель
        </button>
        <button type="button" className="secondary" onClick={() => go('employer')} disabled={!!busy}>
          {busy === 'employer' ? <span className="spinner" /> : <Icon name="inbox" />} Работодатель
        </button>
      </div>
      <div className="field-hint">Новый пустой аккаунт без почты: можно самому пройти тест и подбор с нуля.</div>
    </div>
  )
}

const DEMO_PASSWORD = 'demo12345'
const DEMO_ACCOUNTS = [
  { email: 'candidate@demo.ru', role: 'Соискатель', note: 'с нуля: опрос → тест → категория', icon: 'user', color: '#402fff' },
  { email: 'cand3@demo.ru', role: 'Соискатель', note: 'с категорией и достижениями ФСП', icon: 'trophy', color: '#0ea5a4' },
  { email: 'employer@demo.ru', role: 'Работодатель', note: '«Цифровой Банк»: вакансии и подборка', icon: 'inbox', color: '#ec1d35' },
]

function DemoHint({ onPick, onLogin, busy }: { onPick: (email: string) => void; onLogin: (email: string) => void; busy: string }) {
  const copy = () => {
    navigator.clipboard?.writeText(DEMO_PASSWORD).then(() => toast('Пароль скопирован')).catch(() => {})
  }
  return (
    <div className="demo-hint">
      <div className="row between" style={{ flexWrap: 'nowrap' }}>
        <strong className="mono">demo-аккаунты</strong>
        <button type="button" className="pass-chip" onClick={copy} title="Скопировать пароль">
          пароль <code>{DEMO_PASSWORD}</code> <Icon name="task" />
        </button>
      </div>
      {DEMO_ACCOUNTS.map((a) => (
        <div key={a.email} className="demo-acc" style={{ '--c': a.color } as React.CSSProperties}>
          <span className="tile"><Icon name={a.icon} /></span>
          <button type="button" className="acc-txt" onClick={() => onPick(a.email)} title="Подставить в форму">
            <b>{a.email}</b><small>{a.role} · {a.note}</small>
          </button>
          <button type="button" className="sm" onClick={() => onLogin(a.email)} disabled={!!busy} aria-label={`Войти как ${a.email}`}>
            {busy === a.email ? <span className="spinner" /> : <>Войти <span className="arrow">→</span></>}
          </button>
        </div>
      ))}
      <div className="field-hint">ФСП ID: логин <code>FSP-102347</code>, пароль тот же. Нажмите на email, чтобы подставить его в форму.</div>
    </div>
  )
}

function Login() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const login = async (em: string, pw: string) => {
    setBusy(em || 'form')
    setErr('')
    try {
      const r = await api('/auth/login', { body: { email: em, password: pw } })
      session.set(r.access_token, r.role)
      toast(`Добро пожаловать, ${r.role === 'candidate' ? 'соискатель' : 'работодатель'}`)
      nav(r.role === 'candidate' ? '/c' : '/e', { viewTransition: true })
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy('')
    }
  }
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    login(email, password)
  }
  const pick = (em: string) => {
    setEmail(em)
    setPassword(DEMO_PASSWORD)
    toast('Данные подставлены — нажмите «Войти»')
  }
  return (
    <div className="page">
      <div className="auth">
        <AuthSide title="С возвращением" text="Войдите, чтобы продолжить путь к категории или посмотреть подборку кандидатов." />
        <form className="auth-form stack" onSubmit={submit}>
          <h2>Вход</h2>
          <FspIdButton label="Войти через ФСП ID" />
          <div className="divider">или по email</div>
          <ErrorBox error={err} />
          <div><label htmlFor="login-email">Email</label><input id="login-email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" required /></div>
          <div><label htmlFor="login-pass">Пароль</label><input id="login-pass" value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" required /></div>
          <button className="lg" disabled={!!busy}>{busy === email && busy ? <span className="spinner" /> : 'Войти'}</button>
          <DemoHint onPick={pick} onLogin={(em) => login(em, DEMO_PASSWORD)} busy={busy} />
          <QuickLogin />
          <p className="small muted">Нет аккаунта? <NavLink to="/register" viewTransition>Регистрация</NavLink></p>
        </form>
      </div>
    </div>
  )
}

function Register() {
  const [params] = useSearchParams()
  const [role, setRole] = useState<Role>((params.get('role') as Role) || 'candidate')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState<{ token?: string } | null>(null)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const r = await api('/auth/register', { body: { email, password, role, consent_processing: consent } })
      setDone({ token: r.dev_verify_token })
    } catch (e: any) {
      setErr(e.message)
    }
  }
  if (done)
    return (
      <div className="page" style={{ maxWidth: 480 }}>
        <div className="card stack">
          <h2>Подтвердите email</h2>
          <p>Мы отправили письмо на {email}. Перейдите по ссылке из письма.</p>
          {done.token && (
            <div className="alert info small">
              Демо-режим: <NavLink to={`/verify?token=${done.token}`}>подтвердить сразу</NavLink>
            </div>
          )}
        </div>
      </div>
    )
  return (
    <div className="page">
      <div className="auth">
        <AuthSide
          title={role === 'candidate' ? 'Покажите навыки — работодатели напишут сами' : 'Находите специалистов по подтверждённым навыкам'}
          text={role === 'candidate'
            ? 'Тест по специализации, категория и достижения ФСП в одном профиле. Контакты открываются только с вашего согласия.'
            : 'Опишите потребность своими словами — система разберёт её и покажет подходящие категории кандидатов.'}
        />
        <form className="auth-form stack" onSubmit={submit}>
          <h2>Регистрация</h2>
          <ErrorBox error={err} />
          <div className="role-switch" role="radiogroup" aria-label="Роль">
            <span className={`thumb ${role === 'employer' ? 'right' : ''}`} />
            <button type="button" role="radio" aria-checked={role === 'candidate'} className={role === 'candidate' ? 'on' : ''} onClick={() => setRole('candidate')}>Соискатель</button>
            <button type="button" role="radio" aria-checked={role === 'employer'} className={role === 'employer' ? 'on' : ''} onClick={() => setRole('employer')}>Работодатель</button>
          </div>
          {role === 'candidate' && <><FspIdButton label="Регистрация через ФСП ID" /><div className="divider">или по email</div></>}
          <div><label htmlFor="reg-email">Email</label><input id="reg-email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" required /></div>
          <div><label htmlFor="reg-pass">Пароль (от 8 символов)</label><input id="reg-pass" value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="new-password" minLength={8} required /></div>
          <label className="row" style={{ fontWeight: 400 }}>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            Даю согласие на обработку персональных данных (152-ФЗ)
          </label>
          <button className="lg" disabled={!consent}>Зарегистрироваться</button>
          <p className="small muted">Уже есть аккаунт? <NavLink to="/login" viewTransition>Войти</NavLink></p>
        </form>
      </div>
    </div>
  )
}

function Verify() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [err, setErr] = useState('')
  const started = useRef(false)
  useEffect(() => {
    // Токен одноразовый: StrictMode вызывает эффект дважды
    if (started.current) return
    started.current = true
    api('/auth/verify-email', { body: { token: params.get('token') } })
      .then((r) => {
        session.set(r.access_token, r.role)
        toast('Email подтверждён')
        nav(r.role === 'candidate' ? '/c' : '/e/company')
      })
      .catch((e) => setErr(e.message))
  }, [params, nav])
  return <div className="page"><ErrorBox error={err} />{!err && <p className="row"><span className="spinner" /> Подтверждаем…</p>}</div>
}

export default function App() {
  const loc = useLocation()
  const lang = useLang()
  useEffect(() => { window.scrollTo({ top: 0 }) }, [loc.pathname])
  // При смене языка оболочка перемонтируется: на RU возвращается исходный текст, на EN его переводит i18n
  return (
    <Fragment key={lang}>
      <Backdrop />
      <TopBar />
      <main className="route" key={loc.pathname}>
        <Routes location={loc}>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/fsp-id/login" element={<FspIdLogin />} />
          <Route path="/auth/fsp-callback" element={<FspCallback />} />
          <Route path="/c" element={<Guard role="candidate"><CandidateHome /></Guard>} />
          <Route path="/c/profile" element={<Guard role="candidate"><CandidateProfile /></Guard>} />
          <Route path="/c/survey" element={<Guard role="candidate"><Survey /></Guard>} />
          <Route path="/c/test/:id" element={<Guard role="candidate"><TestRun /></Guard>} />
          <Route path="/c/invitations" element={<Guard role="candidate"><CandidateInvitations /></Guard>} />
          <Route path="/c/vacancies" element={<Guard role="candidate"><Vacancies /></Guard>} />
          <Route path="/c/settings" element={<Guard role="candidate"><Settings /></Guard>} />
          <Route path="/e" element={<Guard role="employer"><EmployerHome /></Guard>} />
          <Route path="/e/needs/:id" element={<Guard role="employer"><NeedPage /></Guard>} />
          <Route path="/e/search" element={<Guard role="employer"><Search /></Guard>} />
          <Route path="/e/invitations" element={<Guard role="employer"><EmployerInvitations /></Guard>} />
          <Route path="/e/tasks" element={<Guard role="employer"><Tasks /></Guard>} />
          <Route path="/e/company" element={<Guard role="employer"><Company /></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
      <Toasts />
    </Fragment>
  )
}
