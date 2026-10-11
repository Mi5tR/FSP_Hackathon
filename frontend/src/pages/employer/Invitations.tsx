import { useState } from 'react'
import { api, fmtDate, STATUS_TITLES } from '../../api'
import { Funnel } from '../candidate/Invitations'
import { Chat, Empty, ErrorBox, Icon, PageHead, Pending, Salary, StatusBadge, toast, useApi } from '../../ui'

const DECLINE: Record<string, string> = {
  salary: 'не подошла зарплата', stack: 'не подошёл стек', company: 'не интересна компания',
  not_looking: 'сейчас не ищет работу', other: 'другое',
}

export default function EmployerInvitations() {
  const { data, error, reload } = useApi<any[]>('/employer/invitations')
  const [chat, setChat] = useState<number | null>(null)
  const withdraw = async (id: number) => {
    await api(`/employer/invitations/${id}/withdraw`, { body: {} })
    toast('Приглашение отозвано')
    reload()
  }
  const advance = async (id: number, to: 'offer' | 'hired') => {
    try {
      await api(`/employer/invitations/${id}/${to}`, { body: {} })
      toast(to === 'offer' ? 'Оффер отмечен — кандидат видит это у себя' : 'Выход на работу отмечен')
      reload()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }
  if (!data) return <Pending error={error} />
  const counts = data.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.status]: (acc[i.status] ?? 0) + 1 }), {})
  return (
    <div className="page">
      <PageHead kicker="// исходящие" title="Приглашения">
        Все отправленные приглашения, их статусы и переписка с кандидатами. После собеседований отметьте оффер и выход
        на работу — кандидат видит актуальный статус, а компания получает сигнал доверия. Контакты появляются после того, как кандидат
        принял приглашение, и исчезают, если он отозвал доступ.
      </PageHead>
      <div className="row stagger" style={{ marginBottom: 16 }}>
        {Object.entries(counts).map(([s, n]) => <span key={s} className="badge">{STATUS_TITLES[s]}: {n}</span>)}
      </div>
      <ErrorBox error={error} />
      {!data.length && <Empty icon="mail" title="Вы ещё никого не пригласили">Найдите кандидатов в подборке по потребности или в банке кандидатов.</Empty>}
      <div className="stack stagger">
        {data.map((i) => (
          <div key={i.id} className="card spot" style={{ margin: 0 }}>
            <div className="row between" style={{ alignItems: 'flex-start' }}>
              <div className="stack" style={{ gap: 4 }}>
                {i.candidate_contacts ? (
                  <>
                    <strong>{i.candidate_contacts.full_name}</strong>
                    <div className="small">{i.candidate_contacts.email} · {i.candidate_contacts.phone} · {i.candidate_contacts.telegram}</div>
                  </>
                ) : (
                  <>
                    <strong>Кандидат #{i.candidate_id}</strong>
                    {i.status === 'accepted' && i.contacts_revoked_at && <div className="small" style={{ color: 'var(--warn)' }}>Кандидат отозвал доступ к контактам {fmtDate(i.contacts_revoked_at)}</div>}
                  </>
                )}
                <div className="small muted">{i.position_title} · отправлено {fmtDate(i.created_at)}</div>
                <Salary from={i.salary_from} to={i.salary_to} />
                <Funnel status={i.status} />
              </div>
              <div className="row">
                <StatusBadge status={i.status} titles={STATUS_TITLES} />
                <button className="secondary sm" onClick={() => setChat(chat === i.id ? null : i.id)} aria-expanded={chat === i.id}>
                  <Icon name="chat" /> Переписка{i.messages_count ? ` (${i.messages_count})` : ''}{i.unread ? <span className="nav-dot">{i.unread}</span> : null}
                </button>
                {['sent', 'viewed'].includes(i.status) && <button className="danger sm" onClick={() => withdraw(i.id)}>Отозвать</button>}
                {i.status === 'accepted' && <button className="sm" onClick={() => advance(i.id, 'offer')}>Сделать оффер</button>}
                {['accepted', 'offer'].includes(i.status) && <button className="secondary sm" onClick={() => advance(i.id, 'hired')}>Вышел на работу</button>}
              </div>
            </div>
            {i.decline_reason && <div className="small muted">причина отказа: {DECLINE[i.decline_reason] ?? i.decline_reason}</div>}
            {chat === i.id && (
              <div style={{ marginTop: 12 }}>
                <Chat base={`/employer/invitations/${i.id}`} me="employer" disabled={['declined', 'withdrawn', 'expired'].includes(i.status)} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
