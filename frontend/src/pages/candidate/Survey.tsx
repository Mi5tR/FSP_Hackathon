import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, GRADE_TITLES } from '../../api'
import { ErrorBox, PageHead, Pending, Tips, useApi } from '../../ui'

const TASKS: Record<string, string[]> = {
  backend: ['Проектирование API', 'Работа с БД', 'Интеграции', 'Highload', 'Микросервисы'],
  frontend: ['Вёрстка', 'SPA', 'Дизайн-системы', 'Производительность', 'SSR'],
  mobile: ['Android', 'iOS', 'Кроссплатформа', 'Офлайн-режим', 'Публикация в сторах'],
  data: ['Аналитика', 'Классический ML', 'Deep Learning', 'A/B-тесты', 'MLOps'],
  analyst: ['Сбор требований', 'BPMN / UML', 'SQL-отчёты', 'Продуктовые метрики', 'A/B-тесты'],
  qa: ['Ручное тестирование', 'Автотесты', 'API-тесты', 'Нагрузочное'],
  devops: ['CI/CD', 'Kubernetes', 'Мониторинг', 'Облака', 'Сети'],
  security: ['Пентест', 'SOC / SIEM', 'Сетевая безопасность', 'Криптография', 'CTF'],
}

export default function Survey() {
  const nav = useNavigate()
  const catalog = useApi<any>('/catalog')
  const hint = useApi<any>('/candidate/grade-hint')
  const [industry, setIndustry] = useState('')
  const [spec, setSpec] = useState('')
  const [grade, setGrade] = useState('')
  const [tasks, setTasks] = useState<string[]>([])
  const [self, setSelf] = useState<Record<string, number>>({})
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const c = catalog.data
  if (!c) return <Pending error={catalog.error} />

  const specs = c.specializations.filter((s: any) => !industry || s.industry === industry)
  const questions: string[] = spec ? c.survey?.[spec] ?? [] : []
  const answered = Object.keys(self).length
  const selfMean = answered ? Object.values(self).reduce((a, b) => a + b, 0) / answered : null
  const pickSpec = (code: string) => {
    const sp = c.specializations.find((s: any) => s.code === code)
    if (sp) setIndustry(sp.industry)
    setSpec(code)
    setSelf({})
    setTasks([])
  }
  const submit = async () => {
    setBusy(true)
    try {
      await api('/candidate/survey', { body: { industry, specialization: spec, claimed_grade: grade, answers: { tasks, self } } })
      const r = await api('/candidate/assessments', { body: {} })
      nav(`/c/test/${r.assessment.id}`, { viewTransition: true })
    } catch (e: any) {
      setErr(e.message)
      setBusy(false)
    }
  }
  const mlSpecs: any[] = hint.data?.specializations ?? []

  return (
    <div className="page">
      <PageHead kicker="// шаг 1 из 3 · опрос" title="Опрос: направление, специализация, грейд">
        Опрос не присваивает категорию — он настраивает тест. Категорию, которую увидит работодатель, даёт только
        результат адаптивного теста. Займёт 2–3 минуты.
      </PageHead>
      <div className="with-aside">
        <div className="stack">
          <div className="card stack spot">
            <h2>1. Направление и специализация</h2>
            <ErrorBox error={err} />
            {mlSpecs.length > 0 && (
              <div className="alert info small">
                По тексту вашего профиля ML-модель предполагает:{' '}
                {mlSpecs.slice(0, 2).map((s: any, k: number) => (
                  <span key={s.specialization}>
                    {k > 0 && ' или '}
                    <a href="#" onClick={(e) => { e.preventDefault(); pickSpec(s.specialization) }}>{s.title}</a> ({Math.round(s.probability * 100)}%)
                  </span>
                ))}. Это подсказка — выбираете вы.
              </div>
            )}
            <div className="grid">
              <div>
                <label>Направление (ИТ-отрасль)</label>
                <select value={industry} onChange={(e) => { setIndustry(e.target.value); setSpec('') }}>
                  <option value="">Выберите…</option>
                  {Object.entries(c.industries).map(([k, v]) => <option key={k} value={k}>{v as string}</option>)}
                </select>
              </div>
              <div>
                <label>Специализация</label>
                <select value={spec} onChange={(e) => pickSpec(e.target.value)}>
                  <option value="">Выберите…</option>
                  {specs.map((s: any) => <option key={s.code} value={s.code}>{s.title}</option>)}
                </select>
              </div>
            </div>
            {spec && (
              <div>
                <label>Чем вы занимаетесь чаще всего?</label>
                <div className="chips">
                  {(TASKS[spec] ?? []).map((t) => (
                    <button key={t} type="button" className={`chip-btn ${tasks.includes(t) ? 'on' : ''}`} aria-pressed={tasks.includes(t)}
                            onClick={() => setTasks(tasks.includes(t) ? tasks.filter((x) => x !== t) : [...tasks, t])}>{t}</button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {spec && questions.length > 0 && (
            <div className="card stack spot" style={{ animation: 'rise .4s var(--ease-out) both' }}>
              <div className="row between">
                <h2 style={{ margin: 0 }}>2. Самооценка опыта</h2>
                <span className="badge neutral">{answered} / {questions.length}</span>
              </div>
              <p className="small muted" style={{ margin: 0 }}>
                Отметьте честно: ответы не влияют на грейд, они помогают подсказать уровень для теста.
              </p>
              <div className="survey-q">
                {questions.map((q, i) => (
                  <div key={i} className="sq-row">
                    <span className="sq-text">{q}</span>
                    <div className="seg sq-scale" role="radiogroup" aria-label={q}>
                      {(c.survey_scale as string[]).map((lbl, v) => (
                        <button key={v} type="button" role="radio" aria-checked={self[i] === v}
                                className={self[i] === v ? 'on' : ''} onClick={() => setSelf({ ...self, [i]: v })}>{lbl}</button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              {selfMean !== null && (
                <div className="field-hint">Средняя самооценка: {selfMean.toFixed(1)} из 3. Подсказка грейда обновится после сохранения опроса.</div>
              )}
            </div>
          )}

          <div className="card stack spot">
            <h2>3. Предполагаемый грейд — выбираете вы, тест подтверждает</h2>
            <div className="grade-pick grade-pick-6">
              {c.grades.map((g: any) => (
                <button key={g.code} type="button" className={grade === g.code ? 'on' : ''} onClick={() => setGrade(g.code)} aria-pressed={grade === g.code}>
                  {hint.data?.grade === g.code && <span className="hint-dot">подсказка</span>}
                  {g.title}<span className="small" style={{ fontWeight: 400, opacity: .8 }}>{g.experience}</span>
                  {hint.data?.distribution?.[g.code] !== undefined && (
                    <span className="gp-bar" aria-hidden="true"><i style={{ width: `${Math.round(hint.data.distribution[g.code] * 100)}%` }} /></span>
                  )}
                </button>
              ))}
            </div>
            {hint.data && (
              <div className="field-hint">
                ML-подсказка: <strong>{GRADE_TITLES[hint.data.grade]}</strong>
                {hint.data.probability ? ` (${Math.round(hint.data.probability * 100)}%)` : ''} — {hint.data.reasons.join(', ')}. {hint.data.note}
              </div>
            )}
            <div className="alert info small">
              Тест адаптивный: 12–22 задания, до 20 минут. Каждый кандидат получает свои варианты заданий. Если грейд
              не подтвердится, он не понижается автоматически: тест на уровень ниже доступен сразу, а профиль можно
              показывать с пометкой «не подтверждён» или скрыть до пересдачи.
            </div>
            <div><button className="lg" disabled={!spec || !grade || busy} onClick={submit}>
              {busy ? <span className="spinner" /> : <>Сохранить и начать тест <span className="arrow">→</span></>}
            </button></div>
          </div>
        </div>
        <Tips title="Как устроен путь" items={[
          ['Опрос', 'Направление и специализация задают банк заданий. Самооценка — только для подсказки.'],
          ['Выбор грейда', 'Шкала из шести ступеней: Intern → Junior → Junior+ → Middle → Middle+ → Senior.'],
          ['Адаптивный тест', 'Сложность подстраивается под ответы; варианты заданий генерируются для каждого заново.'],
          ['Категория', 'Специализация + подтверждённый грейд. Её видят работодатели — и приглашают сами.'],
          ['Смена грейда', 'Не чаще раза в 90 дней. Уверенно сдали — система сразу предложит тест на ступень выше.'],
        ]} />
      </div>
    </div>
  )
}
