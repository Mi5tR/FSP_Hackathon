import { useState } from 'react'
import { api, fmtDate, STATUS_TITLES } from '../../api'
import { MatchBreakdown, ScoreHeadline } from '../../match'
import { Chat, Empty, ErrorBox, Icon, PageHead, Pending, Salary, StatusBadge, toast, useApi } from '../../ui'

const COMPLAINTS: Record<string, string> = {
  fake: 'Вакансии нет: похоже на сбор резюме или данных',
  payment: 'Просят оплату, платное обучение или лишние личные данные',
  conditions: 'Условия в переписке не совпадают с приглашением',
  spam: 'Массовая рассылка, не про мой профиль',
  rude: 'Некорректное общение',
  other: 'Другое',
}
const TRUST_TITLE: Record<string, string> = { high: 'высокое доверие', medium: 'среднее доверие', low: 'низкое доверие', new: 'новая компания', review: 'на проверке' }
const FUNNEL = [['sent', 'Отправлено'], ['viewed', 'Просмотрено'], ['accepted', 'Принято'], ['offer', 'Оффер'], ['hired', 'Выход на работу']]

export function Funnel({ status }: { status: string }) {
  const idx = FUNNEL.findIndex(([k]) => k === status)
  if (idx < 0) return null
  return (
    <div className="funnel" aria-label="Ход взаимодействия">
      {FUNNEL.map(([k, t], i) => (
        <span key={k} style={{ display: 'contents' }}>
          {i > 0 && <i>→</i>}
          <span className={i < idx ? 'done' : i === idx ? 'cur' : ''}>{t}</span>
        </span>
      ))}
    </div>
  )
}

export function TrustBox({ t }: { t: any }) {
  if (!t) return null
  return (
    <div className={`trust-box ${t.level}`}>
      <div className="row between">
        <strong className="row" style={{ gap: 6 }}><Icon name="shield" /> Доверие к работодателю: {TRUST_TITLE[t.level]}</strong>
        <span className="trust-score">{t.score}/100</span>
      </div>
      {t.signals.map((sg: any, i: number) => (
        <div key={i} className={`trust-sig ${sg.ok ? 'ok' : 'no'}`}><b>{sg.ok ? '✓' : '!'}</b><span>{sg.text}</span></div>
      ))}
    </div>
  )
}

const REASONS: Record<string, string> = {
  salary: 'Не подходит зарплата', stack: 'Не подходит стек', company: 'Не интересна компания',
  not_looking: 'Сейчас не ищу работу', other: 'Другое',
}

export default function CandidateInvitations() {
  const { data, error, reload } = useApi<any[]>('/candidate/invitations')
  const [open, setOpen] = useState<any>(null)
  const [reason, setReason] = useState('other')
  const [err, setErr] = useState('')
  const [complaint, setComplaint] = useState<string | null>(null)
  const [complaintText, setComplaintText] = useState('')

  const view = async (id: number) => {
    setOpen(await api(`/candidate/invitations/${id}`))
    reload()
  }
  const act = async (action: 'accept' | 'decline' | 'revoke-contacts' | 'restore-contacts') => {
    setErr('')
    try {
      const r = await api(`/candidate/invitations/${open.id}/${action}`, { body: action === 'decline' ? { reason } : {} })
      setOpen(r)
      reload()
      toast({
        accept: 'Приглашение принято — контакты переданы работодателю',
        decline: 'Приглашение отклонено',
        'revoke-contacts': 'Доступ к контактам отозван',
        'restore-contacts': 'Доступ к контактам восстановлен',
      }[action])
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const sendComplaint = async () => {
    try {
      const r = await api(`/candidate/invitations/${open.id}/complaint`, { body: { reason: complaint, text: complaintText } })
      toast(r.company_paused ? 'Жалоба принята. Приглашения компании приостановлены до проверки' : 'Жалоба принята — спасибо, это защищает других кандидатов')
      setComplaint(null)
      setOpen(await api(`/candidate/invitations/${open.id}`))
      reload()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  if (!data) return <Pending error={error} />
  const chatClosed = open && ['declined', 'withdrawn', 'expired'].includes(open.status)

  return (
    <div className="page">
      <PageHead kicker="// входящие" title="Приглашения от работодателей"
                aside={<span className="badge">{data.length} всего · новых {data.filter((i) => i.status === 'sent').length}</span>}>
        Работодатель пишет первым: позиция, вилка до вычета НДФЛ и разбор, почему вы подходите. Можно задать вопрос
        в переписке до решения — контакты откроются, только если вы примете приглашение.
      </PageHead>
      <ErrorBox error={error} />
      {!data.length && (
        <Empty icon="mail" title="Приглашений пока нет">
          Работодатели находят кандидатов по категории: проверьте, что тест пройден и профиль открыт в настройках приватности.
        </Empty>
      )}
      <div className="grid stagger">
        {data.map((i) => (
          <button key={i.id} className="card stack spot lift" style={{ textAlign: 'left', color: 'inherit', font: 'inherit', fontWeight: 400, display: 'block',
            borderColor: i.status === 'sent' ? 'var(--brand)' : undefined, background: 'var(--card)', minHeight: 0, padding: 22 }} onClick={() => view(i.id)}>
            <div className="row between">
              <strong className="row" style={{ gap: 6 }}>{i.company_name}{i.company_inn_valid && <span className="badge ok" title="ИНН прошёл проверку">ИНН ✓</span>}</strong>
              <StatusBadge status={i.status} titles={STATUS_TITLES} />
            </div>
            {i.match?.percent != null && <div className="small">Соответствие: <strong>{i.match.percent}%</strong></div>}
            <div>{i.position_title}</div>
            <Salary from={i.salary_from} to={i.salary_to} />
            {i.below_expectation && <span className="badge warn">ниже ваших ожиданий</span>}
            {i.company_trust?.level === 'review' && <span className="badge bad">компания на проверке</span>}
            <div className="row between small muted">
              <span>от {fmtDate(i.created_at)}, до {fmtDate(i.expires_at)}</span>
              {i.unread > 0 && <span className="badge live"><Icon name="chat" /> {i.unread} новых</span>}
            </div>
          </button>
        ))}
      </div>

      {open && (
        <div className="modal-bg" onClick={() => setOpen(null)}>
          <div className="modal stack" style={{ maxWidth: 780 }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={open.position_title}>
            <button className="secondary sm close" onClick={() => setOpen(null)} aria-label="Закрыть"><Icon name="x" /></button>
            <div className="row between" style={{ paddingRight: 44 }}><h2 style={{ margin: 0 }}>{open.position_title}</h2><StatusBadge status={open.status} titles={STATUS_TITLES} /></div>
            <div className="row" style={{ gap: 8 }}>
              <strong>{open.company_name}</strong>
              {open.company_inn_valid && <span className="badge ok" title="Добровольная метка доверия: ИНН прошёл проверку контрольной суммы">ИНН проверен</span>}
            </div>
            <Salary from={open.salary_from} to={open.salary_to} big />
            <Funnel status={open.status} />
            {open.salary_flag === 'above_market' && (
              <div className="alert warn small">Вилка заметно выше рынка для вашей категории. Так иногда выглядят «приманки»: уточните условия в переписке до передачи контактов.</div>
            )}
            {open.below_expectation && <div className="alert info small">Верхняя граница вилки ниже ваших зарплатных ожиданий, указанных в профиле.</div>}
            {open.offer_at && <div className="alert ok small">Работодатель сделал оффер {fmtDate(open.offer_at)}{open.hired_at ? `, выход на работу отмечен ${fmtDate(open.hired_at)}` : ''}.</div>}
            <p style={{ whiteSpace: 'pre-wrap' }}>{open.message}</p>
            {open.match?.blocks && (
              <div className="card flat">
                <div className="row" style={{ marginBottom: 10, alignItems: 'center' }}>
                  <ScoreHeadline percent={open.match.percent} probability={open.match.probability} />
                  <div className="small" style={{ flex: 1, minWidth: 220 }}>
                    <strong>Почему вас пригласили.</strong> Так система оценила ваше соответствие потребности работодателя
                    на момент приглашения. Жёлтые и красные навыки можно подтвердить проверкой в разделе «Мой путь».
                  </div>
                </div>
                <MatchBreakdown blocks={open.match.blocks} requirements={open.match.requirements}
                                flags={open.match.flags.filter((f: any) => f.severity !== 'info')} />
              </div>
            )}
            <TrustBox t={open.company_trust} />
            <ErrorBox error={err} />
            {['accepted', 'offer', 'hired'].includes(open.status) && (
              open.contacts_revoked_at ? (
                <div className="alert warn row between">
                  <span>Вы отозвали доступ к контактам {fmtDate(open.contacts_revoked_at)}. Работодатель видит обезличенную карточку.</span>
                  <button className="secondary sm" onClick={() => act('restore-contacts')}>Вернуть доступ</button>
                </div>
              ) : (
                <div className="alert ok row between">
                  <span>Контакты переданы работодателю. Связь: {open.contact_method}</span>
                  <button className="danger sm" onClick={() => act('revoke-contacts')}>Отозвать доступ к контактам</button>
                </div>
              )
            )}
            {['sent', 'viewed'].includes(open.status) && (
              <>
                <div className="small muted">После принятия работодатель увидит ваши контакты (доступ можно отозвать). Связь: {open.contact_method}</div>
                <div className="row">
                  <button onClick={() => act('accept')}>Принять <span className="arrow">→</span></button>
                  <select value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: 'auto' }} aria-label="Причина отказа">
                    {Object.entries(REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <button className="danger" onClick={() => act('decline')}>Отклонить</button>
                </div>
              </>
            )}
            <Chat base={`/candidate/invitations/${open.id}`} me="candidate" disabled={chatClosed} />
            {open.complained ? (
              <div className="small muted"><Icon name="flag" /> Вы пожаловались на это приглашение. Жалоба учитывается в рейтинге доверия компании.</div>
            ) : complaint === null ? (
              <div><button className="secondary sm" onClick={() => setComplaint('fake')}><Icon name="flag" /> Пожаловаться на приглашение</button></div>
            ) : (
              <div className="card flat stack">
                <strong>Жалоба на работодателя</strong>
                <select value={complaint} onChange={(e) => setComplaint(e.target.value)} aria-label="Причина жалобы">
                  {Object.entries(COMPLAINTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <textarea value={complaintText} onChange={(e) => setComplaintText(e.target.value)} placeholder="Что произошло (необязательно)" />
                <div className="small muted">Три жалобы разных кандидатов за 30 дней автоматически приостанавливают приглашения компании до проверки. Активное приглашение будет отклонено.</div>
                <div className="row"><button className="danger" onClick={sendComplaint}>Отправить жалобу</button><button className="secondary" onClick={() => setComplaint(null)}>Отмена</button></div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
