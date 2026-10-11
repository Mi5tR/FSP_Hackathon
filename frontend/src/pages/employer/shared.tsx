import { useState } from 'react'
import { api, download, fmtDate, GRADE_TITLES, SPEC_TITLES, STATUS_TITLES } from '../../api'
import { MatchBreakdown, ScoreHeadline } from '../../match'
import { Category, ErrorBox, Icon, StatusBadge, toast } from '../../ui'

const INTEGRITY_TITLE: Record<string, string> = { ok: 'тест пройден чисто', warn: 'есть сигналы', bad: 'много сигналов' }

function IntegrityBadge({ i }: { i: any }) {
  if (!i?.level) return null
  const cls = i.level === 'ok' ? 'ok' : i.level === 'warn' ? 'warn' : 'bad'
  return (
    <span className={`badge ${cls}`} title={`Уходы с вкладки: ${i.focus_lost}, копирование условия: ${i.copy_attempts}, очень быстрые ответы: ${i.fast_answers}. Это сигнал, а не приговор: на грейд не влияет.`}>
      <Icon name="shield" /> {INTEGRITY_TITLE[i.level]}
    </span>
  )
}

export function CandidateRow({ m, onInvite, onShortlist }: { m: any; onInvite: (m: any) => void; onShortlist?: (m: any) => void }) {
  const [open, setOpen] = useState(false)
  const c = m.candidate
  const bad = m.flags.filter((f: any) => f.severity === 'bad')
  const warn = m.flags.filter((f: any) => f.severity === 'warn')
  return (
    <div className="card spot" style={c.grade_confirmed ? undefined : { borderStyle: 'dashed' }}>
      <div className="row between" style={{ alignItems: 'flex-start' }}>
        <div className="row" style={{ alignItems: 'flex-start', gap: 16 }}>
          <ScoreHeadline percent={m.percent} probability={m.probability} confidence={m.confidence} />
          <div className="stack" style={{ gap: 4 }}>
            <div className="row">
              <strong>{c.display_name}</strong>
              <Category spec={c.specialization} grade={c.grade} confirmed={c.grade_confirmed} />
              {c.is_new && <span className="badge new">новый</span>}
              {c.has_fsp && <span className="badge fsp">ФСП{c.fsp_rank ? ` · ${c.fsp_rank}` : ''}</span>}
              {c.minor_age != null && <span className="badge warn" title="Несовершеннолетний: только лёгкий труд (ст. 63 ТК РФ), согласие представителя получено">до 18 · {c.minor_age} лет</span>}
              <IntegrityBadge i={c.integrity} />
              {m.invitation_status && <StatusBadge status={m.invitation_status} titles={STATUS_TITLES} />}
            </div>
            <div className="small muted">
              {[c.city, c.experience_years != null ? `стаж ${c.experience_years} г.` : null, c.work_format !== 'any' ? c.work_format : null,
                c.last_activity_at ? `активность ${fmtDate(c.last_activity_at)}` : null].filter(Boolean).join(' · ')}
            </div>
          </div>
        </div>
        <div className="row">
          <button className="secondary" title="Стандартизированный PDF-профиль (обезличенный до согласия кандидата)"
                  onClick={() => download(`/employer/candidates/${c.id}/pdf`, `candidate-${c.id}.pdf`).catch((e) => toast(e.message, 'error'))}>PDF</button>
          {onShortlist && (
            <button className="secondary" onClick={() => onShortlist(m)}>{m.shortlisted ? '★ В шорт-листе' : '☆ В шорт-лист'}</button>
          )}
          <button onClick={() => onInvite(m)} title={m.invitation_status ? 'Можно предложить другую позицию' : undefined}>
            {m.invitation_status ? 'Ещё позиция' : 'Пригласить'}
          </button>
        </div>
      </div>
      <div style={{ marginTop: 12 }}>
        <MatchBreakdown blocks={m.blocks} requirements={m.requirements} flags={open ? m.flags : [...bad, ...warn].slice(0, 2)} compact={!open} />
      </div>
      {c.contacts && (
        <div className="alert ok small" style={{ marginTop: 8 }}>
          Контакты: {c.contacts.full_name}, {c.contacts.email}, {c.contacts.phone}, {c.contacts.telegram}
        </div>
      )}
      <button className="secondary sm" style={{ marginTop: 10 }} onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Свернуть' : 'Подробнее: почему такой процент'}
      </button>
      {open && c.achievements?.length > 0 && (
        <ul className="small" style={{ paddingLeft: 18 }}>
          {c.achievements.map((a: any, i: number) => (
            <li key={i}>{a.event_name} · {a.discipline} — {a.place ? `${a.place} место` : 'участие'}{a.participants ? ` из ${a.participants}` : ''}{a.role_in_team ? `, роль: ${a.role_in_team}` : ''}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function InviteModal({ m, need, onClose, onSent }: { m: any; need?: any; onClose: () => void; onSent: () => void }) {
  const [form, setForm] = useState({
    position_title: need?.title ?? '',
    message: need ? `Здравствуйте! Нам понравился ваш профиль для позиции «${need.title}». ${need.description ?? ''}`.slice(0, 600) : '',
    salary_from: need?.salary_from ?? '',
    salary_to: need?.salary_to ?? '',
    contact_method: '',
  })
  const [err, setErr] = useState('')
  const conditions = m.blocks?.find((b: any) => b.key === 'conditions')
  const send = async () => {
    try {
      await api('/employer/invitations', {
        body: { ...form, candidate_id: m.candidate.id, need_id: need?.id ?? null, salary_from: Number(form.salary_from), salary_to: Number(form.salary_to) },
      })
      toast('Приглашение отправлено')
      onSent()
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const set = (k: string, v: any) => setForm({ ...form, [k]: v })
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal stack" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h2>Приглашение: {m.candidate.display_name}</h2>
        <div className="small muted">{SPEC_TITLES[m.candidate.specialization]} · {GRADE_TITLES[m.candidate.grade]} · соответствие {m.percent}%</div>
        <ErrorBox error={err} />
        <div><label>Позиция</label><input value={form.position_title} onChange={(e) => set('position_title', e.target.value)} /></div>
        <div className="row">
          <div style={{ flex: 1 }}><label>Зарплата от, ₽ gross</label><input type="number" value={form.salary_from} onChange={(e) => set('salary_from', e.target.value)} /></div>
          <div style={{ flex: 1 }}><label>до, ₽ gross</label><input type="number" value={form.salary_to} onChange={(e) => set('salary_to', e.target.value)} /></div>
        </div>
        <div className="field-hint">Суммы до вычета НДФЛ (gross) — так кандидат увидит вилку в приглашении.</div>
        {conditions && <div className="small" style={{ color: conditions.score < 1 ? 'var(--warn)' : 'var(--muted)' }}>{conditions.reason}</div>}
        <div><label>Описание предложения</label><textarea value={form.message} onChange={(e) => set('message', e.target.value)} /></div>
        <div><label>Способ связи</label><input value={form.contact_method} onChange={(e) => set('contact_method', e.target.value)} placeholder="Telegram @hr, email, телефон" /></div>
        <div className="small muted">Кандидат сразу увидит условия и разбивку соответствия. Его контакты откроются после того, как он примет приглашение.</div>
        <div className="row"><button onClick={send}>Отправить</button><button className="secondary" onClick={onClose}>Отмена</button></div>
      </div>
    </div>
  )
}
