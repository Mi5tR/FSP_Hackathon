import { useState } from 'react'
import { api, fmtDate, GRADE_TITLES, SPEC_TITLES } from '../../api'
import { Empty, ErrorBox, Icon, PageHead, Pending, toast, useApi } from '../../ui'

const EMPTY = { specialization: 'backend', grade: 'middle', title: '', body: '', skills: '', answer_type: 'open', reference_answer: '' }

function Submissions({ taskId }: { taskId: number }) {
  const subs = useApi<any[]>(`/employer/micro-tasks/${taskId}/submissions`)
  const rate = async (sid: number, rating: number) => {
    await api(`/employer/micro-tasks/submissions/${sid}/rate`, { body: { rating } })
    toast('Оценка сохранена — она станет доказательством навыков кандидата')
    subs.reload()
  }
  if (!subs.data) return <div className="skeleton sk-line" />
  if (!subs.data.length) return <div className="small muted">Ответов пока нет.</div>
  return (
    <div className="stack stagger" style={{ gap: 8 }}>
      {subs.data.map((s) => (
        <div key={s.id} className="card flat" style={{ margin: 0, padding: 14 }}>
          <div className="row between small"><strong>Кандидат #{s.candidate_id}</strong><span className="muted">{fmtDate(s.created_at)}</span></div>
          <p className="small" style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }}>{s.answer}</p>
          {s.auto_checked ? (
            <span className={`badge ${s.employer_rating >= 4 ? 'ok' : 'bad'}`}><Icon name="check" /> проверено системой: {s.employer_rating >= 4 ? 'верно' : 'неверно'}</span>
          ) : (
            <div className="row" style={{ gap: 4 }} role="radiogroup" aria-label="Оценка ответа">
              {[1, 2, 3, 4, 5].map((r) => (
                <button key={r} className={`chip-btn ${s.employer_rating && r <= s.employer_rating ? 'on' : ''}`} style={{ minHeight: 32, padding: '2px 10px' }}
                        onClick={() => rate(s.id, r)} aria-label={`${r} из 5`} role="radio" aria-checked={s.employer_rating === r}>★</button>
              ))}
              <span className="small muted">{s.employer_rating ? `оценка ${s.employer_rating}/5` : 'оцените ответ'}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Tasks() {
  const tasks = useApi<any[]>('/employer/micro-tasks')
  const catalog = useApi<any>('/catalog')
  const [form, setForm] = useState<any>(EMPTY)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const set = (k: string, v: any) => setForm({ ...form, [k]: v })

  const create = async () => {
    setErr('')
    try {
      const skills = form.skills.split(',').map((x: string) => x.trim()).filter(Boolean)
      await api('/employer/micro-tasks', { body: { ...form, skills, reference_answer: form.answer_type === 'exact' ? form.reference_answer : null } })
      setForm(EMPTY)
      tasks.reload()
      toast('Задание опубликовано для категории')
    } catch (e: any) {
      setErr(e.message)
    }
  }
  if (!tasks.data) return <Pending error={tasks.error} />
  const skillCodes: string[] = catalog.data?.skills?.map((s: any) => s.code) ?? []

  return (
    <div className="page">
      <PageHead kicker="// оценка навыков" title="Регулярные задания">
        Короткие задания для категории кандидатов. Если у задания есть эталон, ответ проверяет система; открытые
        ответы (подход, скрипт, бизнес-решение) оцениваете вы по шкале 1–5. Оценки становятся доказательством навыков
        в подборе и поддерживают актуальность профилей.
      </PageHead>
      <div className="card stack spot">
        <h3>Новое задание</h3>
        <ErrorBox error={err} />
        <div className="grid">
          <div><label>Специализация</label>
            <select value={form.specialization} onChange={(e) => set('specialization', e.target.value)}>
              {Object.entries(SPEC_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
          <div><label>Грейд</label>
            <select value={form.grade} onChange={(e) => set('grade', e.target.value)}>
              {Object.entries(GRADE_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
          <div><label>Навыки (коды через запятую)</label>
            <input value={form.skills} onChange={(e) => set('skills', e.target.value)} placeholder="sql, system_design" list="skill-codes" />
            <datalist id="skill-codes">{skillCodes.map((c) => <option key={c} value={c} />)}</datalist></div>
        </div>
        <div><label>Название</label><input value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="Идемпотентность платежа" /></div>
        <div><label>Условие</label><textarea value={form.body} onChange={(e) => set('body', e.target.value)} placeholder="Опишите задачу (от 20 символов)" /></div>
        <div className="row">
          <div className="seg" role="radiogroup" aria-label="Тип проверки">
            <button type="button" className={form.answer_type === 'open' ? 'on' : ''} onClick={() => set('answer_type', 'open')}>Открытый ответ — оцениваю я</button>
            <button type="button" className={form.answer_type === 'exact' ? 'on' : ''} onClick={() => set('answer_type', 'exact')}>С эталоном — проверяет система</button>
          </div>
        </div>
        {form.answer_type === 'exact' && (
          <div style={{ animation: 'rise .35s var(--ease-out) both' }}>
            <label>Эталонный ответ (кандидату не показывается)</label>
            <input value={form.reference_answer} onChange={(e) => set('reference_answer', e.target.value)} placeholder="O(n log n)|n log n" />
            <div className="field-hint">Допустимые варианты через «|». Регистр, пробелы и «ё/е» не учитываются.</div>
          </div>
        )}
        <div><button onClick={create} disabled={form.body.length < 20 || !form.title}>Опубликовать задание <span className="arrow">→</span></button></div>
      </div>

      {!tasks.data.length && <Empty icon="task" title="Заданий пока нет">Создайте первое — оно появится у кандидатов выбранной категории.</Empty>}
      <div className="stack stagger">
        {tasks.data.map((t) => (
          <div key={t.id} className="card" style={{ margin: 0 }}>
            <div className="row between">
              <div>
                <strong>{t.title}</strong>
                <div className="small muted">{SPEC_TITLES[t.specialization]} · {GRADE_TITLES[t.grade]} · {fmtDate(t.created_at)}{t.skills.length ? ` · ${t.skills.join(', ')}` : ''}</div>
              </div>
              <div className="row">
                <span className={`badge ${t.answer_type === 'exact' ? 'ok' : ''}`}>{t.answer_type === 'exact' ? 'автопроверка' : 'открытый ответ'}</span>
                <button className="secondary sm" onClick={() => setOpen(open === t.id ? null : t.id)} aria-expanded={open === t.id}>Ответы: {t.submissions}</button>
              </div>
            </div>
            <p className="small" style={{ margin: '8px 0 0' }}>{t.body}</p>
            {t.reference_answer && <div className="small muted" style={{ marginTop: 6 }}>Эталон: <code>{t.reference_answer}</code></div>}
            {open === t.id && <div style={{ marginTop: 12 }}><Submissions taskId={t.id} /></div>}
          </div>
        ))}
      </div>
    </div>
  )
}
