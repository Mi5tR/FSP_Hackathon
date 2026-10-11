import { useEffect, useState } from 'react'
import { api, fmtDate } from '../../api'
import { TrustBox } from '../candidate/Invitations'
import { ErrorBox, Icon, PageHead, Pending, Tips, toast, useApi } from '../../ui'

const FIELDS: [string, string][] = [
  ['name', 'Название компании'], ['industry', 'Направление деятельности'], ['website', 'Сайт'],
  ['contact_email', 'Контактный email'], ['contact_phone', 'Телефон'], ['inn', 'ИНН (добровольная метка доверия)'],
]
const EVENT_TITLES: Record<string, string> = {
  'applicant.created': 'кандидат передан в ATS', 'applicant.stage': 'этап обновлён в ATS',
  'stage.applied': 'этап из ATS применён', 'stage.ignored': 'событие ATS пропущено', 'vacancies.imported': 'вакансии импортированы',
}

function AtsPanel() {
  const ats = useApi<any>('/employer/ats')
  const [account, setAccount] = useState('')
  const [token, setToken] = useState('')
  const [err, setErr] = useState('')
  const a = ats.data
  const call = async (fn: () => Promise<any>, msg: string) => {
    setErr('')
    try {
      const r = await fn()
      ats.setData(r)
      toast(typeof msg === 'string' ? msg : '')
    } catch (e: any) {
      setErr(e.message)
    }
  }
  if (!a) return <div className="card"><div className="skeleton sk-line" /></div>
  return (
    <div className="card stack spot">
      <div className="row between">
        <h2 style={{ margin: 0 }}><Icon name="link" /> Интеграция с ATS (Huntflow)</h2>
        <span className={`badge ${a.connected ? 'ok' : 'neutral'}`}>{a.connected ? `подключено · ${a.mode === 'live' ? 'рабочий API' : 'демо-режим'}` : 'не подключено'}</span>
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        Кандидат попадает в вашу ATS, как только раскрыты контакты (принял приглашение или откликнулся сам). Этапы
        «Оффер», «Вышел на работу», «Отказ» из ATS приходят вебхуком и обновляют статус у кандидата. Вакансии из ATS
        импортируются черновиками потребностей — без ручного дублирования.
      </p>
      <ErrorBox error={err} />
      {!a.connected ? (
        <div className="grid">
          <div><label>ID аккаунта Huntflow</label><input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="например, 12345" /></div>
          <div><label>API-токен (пусто — демо-режим)</label><input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Bearer-токен Huntflow" /></div>
          <div><button disabled={!account} onClick={() => call(() => api('/employer/ats', { method: 'PUT', body: { account_id: account, token } }), 'ATS подключена')}>Подключить</button></div>
        </div>
      ) : (
        <>
          <div className="small">Аккаунт: <code>{a.account_id}</code> · вебхук для этапов: <code>{a.webhook_url}</code></div>
          <div className="row">
            <button className="secondary" onClick={() => call(async () => { const r = await api('/employer/ats/import-vacancies', { body: {} }); toast(`Импортировано вакансий: ${r.imported}`); return r }, '')}>Импортировать вакансии из ATS</button>
            <button className="danger sm" onClick={() => call(() => api('/employer/ats', { method: 'DELETE' }), 'ATS отключена')}>Отключить</button>
          </div>
          <div>
            <label>Журнал синхронизации</label>
            {a.events.length ? (
              <div className="ats-log">
                {a.events.map((e: any) => (
                  <div key={e.id} title={JSON.stringify(e.payload)}>
                    <span>{e.direction === 'out' ? '→' : '←'}</span>
                    <span>{fmtDate(e.created_at)}</span>
                    <span>{EVENT_TITLES[e.event] ?? e.event}{e.status !== 'ok' ? ` (${e.status})` : ''}</span>
                  </div>
                ))}
              </div>
            ) : <div className="small muted">Событий пока нет.</div>}
          </div>
        </>
      )}
    </div>
  )
}

export default function Company() {
  const { data, error, setData } = useApi<any>('/employer/company')
  const trust = useApi<any>('/employer/trust')
  const [form, setForm] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => { if (data) setForm(data) }, [data])
  if (!form) return <Pending error={error} />
  const save = async () => {
    try {
      const body = Object.fromEntries([...FIELDS.map(([k]) => [k, form[k] || null]), ['description', form.description ?? '']])
      body.name = body.name ?? ''
      body.industry = body.industry ?? ''
      const saved = await api('/employer/company', { method: 'PUT', body })
      setData(saved)
      trust.reload()
      toast(saved.inn_valid ? 'Сохранено. ИНН проверен — кандидаты увидят метку доверия' : 'Профиль компании сохранён')
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const t = trust.data
  return (
    <div className="page">
      <PageHead kicker="// о компании" title="Профиль компании, доверие и ATS">
        Эти данные кандидат видит в приглашении рядом с вилкой. Доверие к компании считается по поведению: проверенный
        ИНН и домен, ответы в переписке, офферы и жалобы кандидатов.
      </PageHead>
      <div className="with-aside">
        <div className="stack">
          {t?.level === 'review' && (
            <div className="alert bad">На компанию поступили жалобы кандидатов ({t.complaints_30d} за 30 дней). Приглашения приостановлены до проверки модератором.</div>
          )}
          <div className="card stack spot">
            <h2>Профиль компании</h2>
            <p className="small muted">Название видно кандидату в приглашении — без него приглашения отправлять нельзя.</p>
            {form.inn && (data?.inn === form.inn) && (
              data?.inn_valid
                ? <div className="alert ok small">ИНН прошёл проверку контрольной суммы — в приглашениях кандидаты видят метку «ИНН проверен». Сверка с ЕГРЮЛ — следующий этап.</div>
                : <div className="alert warn small">ИНН не прошёл проверку контрольной суммы — метка доверия не показывается. Основной сценарий это не блокирует.</div>
            )}
            <ErrorBox error={err} />
            <div className="grid">
              {FIELDS.map(([k, tt]) => <div key={k}><label>{tt}</label><input value={form[k] ?? ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></div>)}
            </div>
            <div><label>О компании и команде</label><textarea value={form.description ?? ''} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
            <div><button onClick={save}>Сохранить</button></div>
          </div>
          {t && (
            <div className="card stack spot">
              <div className="row between">
                <h2 style={{ margin: 0 }}>Как вас видит кандидат</h2>
                <span className="badge neutral">приглашений сегодня: {t.sent_today} из {t.daily_limit}</span>
              </div>
              <TrustBox t={t} />
              <div className="small muted">Лимит приглашений в сутки зависит от доверия: новая компания — 15, средний уровень — 40, высокий — 60.</div>
            </div>
          )}
          <AtsPanel />
        </div>
        <Tips title="Что повышает доверие" items={[
          ['ИНН и домен', 'Верный ИНН и почта на домене сайта компании — две метки доверия в каждом приглашении.'],
          ['Отвечайте в переписке', 'Доля ответов после принятия приглашения видна кандидатам: «гостинг» снижает рейтинг.'],
          ['Отмечайте офферы', 'Офферы и выходы на работу показывают, что компания реально нанимает.'],
          ['Без приманок', 'Вилка сильно выше рынка категории помечается для кандидата как подозрительная.'],
          ['Жалобы', 'Три жалобы разных кандидатов за 30 дней приостанавливают приглашения до проверки.'],
        ]} />
      </div>
    </div>
  )
}
