import { useState } from 'react'
import { api, fmtDate, GRADE_TITLES, SPEC_TITLES, STATUS_TITLES } from '../../api'
import { Empty, ErrorBox, Icon, PageHead, Salary, StatusBadge, toast, useApi } from '../../ui'

function TaskResult({ t }: { t: any }) {
  if (t.auto_checked) {
    return t.my_rating >= 4
      ? <div className="alert ok small">Проверено системой по эталону: верно. Навыки задания учтены в профиле.</div>
      : <div className="alert warn small">Проверено системой по эталону: ответ не совпал с эталоном.</div>
  }
  if (t.my_rating) return <div className="alert ok small">Работодатель оценил ответ: {'★'.repeat(t.my_rating)}{'☆'.repeat(5 - t.my_rating)}</div>
  return <div className="alert info small">Ответ отправлен — открытое задание оценит работодатель.</div>
}

export default function Vacancies() {
  const [spec, setSpec] = useState('')
  const vac = useApi<any[]>(`/vacancies${spec ? `?specialization=${spec}` : ''}`)
  const apps = useApi<any[]>('/candidate/applications')
  const tasks = useApi<any[]>('/candidate/micro-tasks')
  const [err, setErr] = useState('')
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const applied = new Set(apps.data?.map((a) => a.need_id))

  const apply = async (id: number) => {
    setErr('')
    try {
      await api(`/candidate/vacancies/${id}/apply`, { body: { cover_note: '' } })
      apps.reload()
      toast('Отклик отправлен — контакты раскрыты этому работодателю')
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const sendTask = async (t: any) => {
    try {
      const r = await api(`/candidate/micro-tasks/${t.id}/answer`, { body: { answer: answers[t.id] ?? '' } })
      tasks.reload()
      toast(r.result === 'correct' ? 'Верно! Засчитано автоматически' : r.result === 'wrong' ? 'Ответ не совпал с эталоном' : 'Ответ отправлен работодателю',
            r.result === 'wrong' ? 'error' : 'ok')
    } catch (e: any) {
      setErr(e.message)
    }
  }

  return (
    <div className="page">
      <PageHead kicker="// возможности" title="Вакансии и задания"
                aside={<span className="badge">{vac.data?.length ?? 0} вакансий · {tasks.data?.length ?? 0} заданий</span>}>
        Короткие задания от работодателей вашей категории и открытые вакансии. Главный путь — приглашения,
        но здесь можно проявить инициативу самому.
      </PageHead>
      <ErrorBox error={err || vac.error} />
      {!!tasks.data?.length && (
        <div className="card spot">
          <h2>Короткие задания от работодателей</h2>
          <p className="small muted">
            Система адресно предлагает одно задание — по навыку, где в профиле меньше всего данных. Задания с эталонным
            ответом проверяет система сразу, открытые оценивает работодатель. Результат поддерживает
            актуальность профиля и становится доказательством навыков в подборе.
          </p>
          <div className="stack stagger">
            {tasks.data.map((t) => (
              <div key={t.id} className="card flat stack" style={{ margin: 0, ...(t.recommended ? { borderColor: 'var(--accent)' } : {}) }}>
                {t.recommended && <div className="small" style={{ color: 'var(--accent)' }}><Icon name="zap" /> Задание для вас: {t.recommended_reason}</div>}
                <div className="row between">
                  <strong>{t.title}</strong>
                  <span className="row small muted" style={{ gap: 6 }}>
                    <span className={`badge ${t.answer_type === 'exact' ? 'ok' : ''}`}>{t.answer_type === 'exact' ? 'автопроверка' : 'оценит работодатель'}</span>
                    {t.company_name}
                  </span>
                </div>
                <p className="small" style={{ margin: 0 }}>{t.body}</p>
                {t.my_answer ? <TaskResult t={t} /> : (
                  <>
                    {t.answer_type === 'exact'
                      ? <input value={answers[t.id] ?? ''} onChange={(e) => setAnswers({ ...answers, [t.id]: e.target.value })} placeholder="Короткий ответ" aria-label="Ответ" />
                      : <textarea value={answers[t.id] ?? ''} onChange={(e) => setAnswers({ ...answers, [t.id]: e.target.value })} placeholder="Ваш подход…" aria-label="Ответ" />}
                    <div><button onClick={() => sendTask(t)} disabled={(answers[t.id] ?? '').trim().length < (t.answer_type === 'exact' ? 1 : 20)}>
                      Отправить <span className="arrow">→</span></button></div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="row between">
        <h1>Открытые вакансии</h1>
        <select value={spec} onChange={(e) => setSpec(e.target.value)} style={{ width: 220 }} aria-label="Специализация">
          <option value="">Все специализации</option>
          {Object.entries(SPEC_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <p className="small muted">Основной путь — приглашения от работодателей. Откликнуться самостоятельно можно, пока приглашений нет. Вакансии размещают работодатели платформы, сторонние площадки не агрегируются.</p>
      {vac.data && !vac.data.length && <Empty icon="inbox" title="Вакансий по этой специализации нет" />}
      <div className="grid stagger">
        {vac.data?.map((v) => (
          <div key={v.id} className="card stack spot lift">
            <strong>{v.title}</strong>
            <div className="small muted">{v.company_name} · {SPEC_TITLES[v.specialization]} · {GRADE_TITLES[v.grade]}</div>
            <Salary from={v.salary_from} to={v.salary_to} />
            <div className="small">{v.description}</div>
            {applied.has(v.id) ? <span className="badge ok"><Icon name="check" /> Вы откликнулись</span> : <div><button onClick={() => apply(v.id)}>Откликнуться</button></div>}
          </div>
        ))}
      </div>

      {!!apps.data?.length && (
        <div className="card" data-reveal>
          <h2>Мои отклики</h2>
          <table>
            <thead><tr><th>Вакансия</th><th>Компания</th><th>Дата</th><th>Статус</th></tr></thead>
            <tbody>
              {apps.data.map((a) => (
                <tr key={a.id}><td>{a.vacancy_title}</td><td>{a.company_name}</td><td>{fmtDate(a.created_at)}</td><td><StatusBadge status={a.status} titles={STATUS_TITLES} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
