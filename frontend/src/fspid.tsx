/**
 * Вход через ФСП ID по OpenID Connect (Authorization Code Flow).
 * Боевого Keycloak ФСП нет, поэтому по умолчанию экран входа — имитация (/fsp-id/login),
 * а бэкенд выдаёт одноразовый code. С реальным Keycloak меняется только authorize_url из /auth/fsp-id/config.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, session } from './api'
import { ErrorBox, Icon, LogoMark, toast } from './ui'

const STATE_KEY = 'fsp_oidc_state'
const CALLBACK = '/auth/fsp-callback'

function randomState() {
  const a = new Uint8Array(16)
  crypto.getRandomValues(a)
  return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function FspIdButton({ label }: { label: string }) {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const start = async () => {
    setBusy(true)
    const state = randomState()
    try { sessionStorage.setItem(STATE_KEY, state) } catch { /* без sessionStorage проверка state невозможна */ }
    try {
      const cfg = await api(`/auth/fsp-id/config?${new URLSearchParams({ state, redirect_uri: CALLBACK })}`)
      if (cfg.mode === 'mock') nav(cfg.authorize_url, { viewTransition: true })
      else window.location.assign(cfg.authorize_url)
    } catch (e: any) {
      toast(e.message, 'error')
      setBusy(false)
    }
  }
  return (
    <button type="button" className="btn fsp lg" onClick={start} disabled={busy} style={{ width: '100%' }}>
      {busy ? <span className="spinner" /> : <LogoMark className="" />}
      {label}
    </button>
  )
}

/** Имитация экрана входа ФСП ID (в проде эту страницу показывает Keycloak ФСП). */
export function FspIdLogin() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [login, setLogin] = useState('FSP-102347')
  const [password, setPassword] = useState('demo12345')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const state = params.get('state') ?? ''
  const redirect = params.get('redirect_uri') ?? CALLBACK
  const linking = !!session.token
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    try {
      const r = await api('/auth/fsp-id/mock-authorize', { body: { login, password, state, redirect_uri: redirect } })
      nav(`${redirect}?${new URLSearchParams({ code: r.code, state: r.state })}`, { viewTransition: true })
    } catch (e: any) {
      setErr(e.message)
      setBusy(false)
    }
  }
  return (
    <div className="page">
      <div className="idp">
        <form className="idp-card stack" onSubmit={submit}>
          <div className="idp-head"><LogoMark /><div><b>ФСП ID</b><div className="small muted">единый аккаунт Федерации</div></div></div>
          <div className="small muted">Приложение <strong>«ФСП Карьера»</strong> запрашивает доступ:</div>
          <div className="scope"><Icon name="user" /><span>Имя и email из профиля ФСП ID</span></div>
          <div className="scope"><Icon name="trophy" /><span>Результаты соревнований: места, дисциплины, командные результаты</span></div>
          <ErrorBox error={err} />
          <div><label htmlFor="idp-login">Email или ФСП ID</label><input id="idp-login" value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" required /></div>
          <div><label htmlFor="idp-pass">Пароль</label><input id="idp-pass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
          <button className="lg" disabled={busy || !state}>{busy ? <span className="spinner" /> : linking ? 'Разрешить и привязать' : 'Разрешить и войти'}</button>
          <div className="small muted">
            Нажимая кнопку, вы соглашаетесь передать эти данные «ФСП Карьере» для обработки по 152-ФЗ.
            ID, оканчивающийся на 0, — участник без истории соревнований.
          </div>
        </form>
        <div className="idp-banner">имитация Keycloak ФСП ID · OpenID Connect · пароль в демо: demo12345</div>
      </div>
    </div>
  )
}

export function FspCallback() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [err, setErr] = useState('')
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return // код одноразовый, а StrictMode вызывает эффект дважды
    started.current = true
    let expected: string | null = null
    try { expected = sessionStorage.getItem(STATE_KEY); sessionStorage.removeItem(STATE_KEY) } catch { /* нет хранилища */ }
    const state = params.get('state') ?? ''
    if (!expected || expected !== state) {
      setErr('Параметр state не совпадает — вход прерван (защита от CSRF). Попробуйте ещё раз.')
      return
    }
    const linking = !!session.token
    api('/auth/fsp-id/callback', { body: { code: params.get('code'), state } })
      .then((r) => {
        session.set(r.access_token, r.role)
        toast(linking ? 'ФСП ID привязан, достижения загружены' : 'Вы вошли через ФСП ID')
        nav(linking ? '/c/settings' : '/c', { replace: true })
      })
      .catch((e) => setErr(e.message))
  }, [params, nav])
  return (
    <div className="page" style={{ maxWidth: 520 }}>
      {err ? <ErrorBox error={err} /> : <div className="card row"><span className="spinner" /> Получаем профиль из ФСП ID…</div>}
    </div>
  )
}
