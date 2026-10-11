import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, fmtDate, GRADE_TITLES, SPEC_TITLES } from '../../api'
import { RequirementsEditor } from '../../match'
import { Empty, ErrorBox, Kpi, PageHead, Salary, Tips, toast, useApi } from '../../ui'

const EXAMPLE = 'Ищем middle backend-разработчика на Python (FastAPI) в команду платежей: PostgreSQL, REST API, asyncio. Зарплата 230 000 – 320 000 руб.'

export default function EmployerHome() {
  const nav = useNavigate()
  const needs = useApi<any[]>('/employer/needs')
  const invs = useApi<any[]>('/employer/invitations')
  const [text, setText] = useState('')
  const [draft, setDraft] = useState<any>(null)
  const [err, setErr] = useState('')
  const [ml, setMl] = useState<any>(null)

  const parse = async () => {
    setErr('')
    try {
      const p = await api('/employer/needs/parse', { body: { text } })
      setMl({ spec: p.specialization_ml?.[0], suggested: p.suggested_skills ?? [], specFromText: !!p.specialization })
      setDraft({
        title: '', description: text, specialization: p.specialization ?? p.specialization_ml?.[0]?.specialization ?? 'backend', grade: p.grade ?? 'middle',
        requirements: p.requirements.map((r: any) => ({ skill: r.skill, importance: r.importance, level: r.level })),
        work_format: p.work_format ?? 'any',
        salary_from: p.salary_from ?? '', salary_to: p.salary_to ?? '', is_published: false,
      })
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const create = async () => {
    try {
      const n = await api('/employer/needs', {
        body: {
          ...draft,
          title: draft.title || `${SPEC_TITLES[draft.specialization]} ${GRADE_TITLES[draft.grade]}`,
          salary_from: Number(draft.salary_from), salary_to: Number(draft.salary_to),
        },
      })
      toast('Потребность создана — подборка готова')
      nav(`/e/needs/${n.id}`, { viewTransition: true })
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const set = (k: string, v: any) => setDraft({ ...draft, [k]: v })

  return (
    <div className="page">
      <PageHead kicker="// кабинет работодателя" title="Потребности и подбор">
        Опишите, кого ищете, обычным текстом — система разберёт стек, уровень и вилку, покажет подходящие категории
        и объяснит, почему каждый кандидат в подборке.
      </PageHead>
      <div className="kpis stagger">
        <Kpi value={needs.data?.length} label="потребностей" hint={`опубликовано вакансий: ${needs.data?.filter((n) => n.is_published).length ?? 0}`} icon="star" color="#402fff" />
        <Kpi value={invs.data?.length} label="приглашений отправлено" hint="лимит в сутки зависит от доверия к компании" icon="mail" color="#ec1d35" />
        <Kpi value={invs.data?.filter((i) => ['accepted', 'offer', 'hired'].includes(i.status)).length} label="принято кандидатами" hint="контакты открыты" icon="check" color="#0ea5a4" />
        <Kpi value={invs.data?.reduce((s, i) => s + (i.unread ?? 0), 0)} label="непрочитанных сообщений" hint="в переписке по приглашениям" icon="chat" color="#f59e0b" />
      </div>
      <div className="with-aside">
      <div className="card stack spot">
        <h2>Опишите, кого ищете</h2>
        <p className="small muted">Своими словами: чем занимается команда, стек, уровень, вилка. Система разберёт текст и подберёт категории кандидатов.</p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE} />
        <div className="row">
          <button onClick={parse} disabled={text.length < 10}>Разобрать</button>
          <button className="secondary" onClick={() => setText(EXAMPLE)}>Пример</button>
        </div>
        <ErrorBox error={err} />
        {draft && (
          <div className="stack" style={{ borderTop: '1px solid var(--border)', paddingTop: 16, animation: 'rise .45s var(--ease-out) both' }}>
            <div className="alert info small">
              Проверьте, как система поняла запрос, и при необходимости поправьте.
              {ml?.spec && <> NLP-модель: <strong>{ml.spec.title}</strong> ({Math.round(ml.spec.probability * 100)}%){!ml.specFromText && ' — специализация в тексте не названа, взята по модели'}.</>}
            </div>
            {ml?.suggested?.length > 0 && (
              <div className="small">
                Возможно, вы имели в виду (распознано по сходству написания):{' '}
                {ml.suggested.map((x: any) => (
                  <button key={x.skill} type="button" className="chip-btn" style={{ marginRight: 6 }}
                          onClick={() => { set('requirements', [...draft.requirements, { skill: x.skill, importance: 'must', level: 'confident' }]); setMl({ ...ml, suggested: ml.suggested.filter((y: any) => y.skill !== x.skill) }) }}>
                    + {x.title} <span className="muted">«{x.matched}»</span>
                  </button>
                ))}
              </div>
            )}
            <div className="grid">
              <div><label>Название</label><input value={draft.title} onChange={(e) => set('title', e.target.value)} placeholder="Backend-разработчик" /></div>
              <div>
                <label>Специализация</label>
                <select value={draft.specialization} onChange={(e) => set('specialization', e.target.value)}>
                  {Object.entries(SPEC_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div>
                <label>Грейд</label>
                <select value={draft.grade} onChange={(e) => set('grade', e.target.value)}>
                  {Object.entries(GRADE_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div>
                <label>Формат работы</label>
                <select value={draft.work_format} onChange={(e) => set('work_format', e.target.value)}>
                  <option value="any">Любой</option><option value="remote">Удалённо</option>
                  <option value="hybrid">Гибрид</option><option value="office">Офис</option>
                </select>
              </div>
              <div><label>Зарплата от, ₽ gross</label><input type="number" value={draft.salary_from} onChange={(e) => set('salary_from', e.target.value)} /></div>
              <div><label>до, ₽ gross (до вычета НДФЛ)</label><input type="number" value={draft.salary_to} onChange={(e) => set('salary_to', e.target.value)} /></div>
            </div>
            <div>
              <label>Требования к навыкам (извлечены из текста — поправьте при необходимости)</label>
              <RequirementsEditor value={draft.requirements} onChange={(v) => set('requirements', v)} />
            </div>
            <label className="row" style={{ fontWeight: 400 }}>
              <input type="checkbox" checked={draft.is_published} onChange={(e) => set('is_published', e.target.checked)} /> Также опубликовать как открытую вакансию
            </label>
            <button onClick={create} disabled={!draft.salary_from || !draft.salary_to}>Создать и показать подборку</button>
          </div>
        )}
      </div>

      <Tips title="Как получить сильную подборку" items={[
        ['Пишите как для человека', '«Middle Python, платежи, PostgreSQL, вилка 230–320» — разбор поймёт стек, грейд и деньги.'],
        ['Отметьте обязательное', 'Обязательные навыки нельзя «перекрыть» сильными сторонами — так в топ не попадут случайные люди.'],
        ['Смотрите смежные категории', 'Junior+ и Senior− часто дают сильных кандидатов, которых нет в точной категории.'],
        ['Приглашайте адресно', 'Вилка до НДФЛ и понятная позиция заметно повышают долю принятых приглашений.'],
      ]} />
      </div>

      <h2>Мои потребности</h2>
      <ErrorBox error={needs.error} />
      {needs.data && !needs.data.length && <Empty icon="inbox" title="Потребностей пока нет">Опишите, кого ищете, — система подберёт категории и кандидатов.</Empty>}
      <div className="grid stagger">
        {needs.data?.map((n) => (
          <Link key={n.id} to={`/e/needs/${n.id}`} className="card stack" viewTransition>
            <div className="row between"><strong>{n.title}</strong>{n.is_published && <span className="badge ok">Опубликована</span>}</div>
            <div className="small muted">{SPEC_TITLES[n.specialization]} · {GRADE_TITLES[n.grade]}</div>
            <div className="row" style={{ gap: 4 }}>
              {n.requirements.map((r: any) => <span key={r.skill} className={`req ok ${r.importance === 'nice' ? 'nice' : ''}`}>{r.skill}</span>)}
            </div>
            <Salary from={n.salary_from} to={n.salary_to} />
            <div className="small muted">создана {fmtDate(n.created_at)}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}
