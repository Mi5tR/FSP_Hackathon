import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, fmtDate, GRADE_TITLES, SPEC_TITLES } from '../../api'
import { Category, ErrorBox, Icon, Kpi, PageHead, Pending, SkillChips, Tips, toast, useApi } from '../../ui'

const OUTCOME: Record<string, [string, string]> = {
  confirmed: ['Подтверждён', 'ok'],
  upgrade_eligible: ['Подтверждён уверенно', 'ok'],
  not_confirmed: ['Не подтверждён', 'warn'],
  skill_checked: ['Навык проверен', 'ok'],
}

const CHECK_STATUS: Record<string, [string, string]> = {
  verified: ['подтверждён тестом', 'ok'],
  testable: ['можно проверить', 'warn'],
  not_testable: ['проверки пока нет', ''],
}

function SkillChecks({ onStart, disabled }: { onStart: (skill: string) => void; disabled: boolean }) {
  const checks = useApi<any[]>('/candidate/skill-checks')
  if (!checks.data?.length) return null
  const toCheck = checks.data.filter((c) => c.status === 'testable')
  return (
    <div className="card">
      <h3>Навыки из резюме</h3>
      <p className="small muted">
        В подборе навык, который только указан в резюме, весит мало. Короткая проверка (4–6 заданий, грейд не меняется)
        превращает его в подтверждённый. {toCheck.length > 0 && `Можно проверить: ${toCheck.length}.`}
      </p>
      <table>
        <thead><tr><th>Навык</th><th>Статус</th><th>Нужен в вакансиях</th><th /></tr></thead>
        <tbody>
          {checks.data.map((c) => (
            <tr key={c.skill}>
              <td>{c.title}{c.tested_as && <span className="small muted"> · проверяется через {c.tested_as}</span>}</td>
              <td><span className={`badge ${CHECK_STATUS[c.status][1]}`}>{CHECK_STATUS[c.status][0]}</span>
                {c.level != null && <span className="small muted"> уровень {Math.round(c.level * 100)}%</span>}</td>
              <td>{c.demanded || '—'}</td>
              <td>{c.status === 'testable' && <button className="secondary" disabled={disabled} onClick={() => onStart(c.skill)}>Проверить</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TaskOfWeek() {
  const tasks = useApi<any[]>('/candidate/micro-tasks')
  const t = tasks.data?.find((x) => x.recommended)
  if (!t) return null
  return (
    <div className="card spot" style={{ borderLeft: '4px solid var(--accent)' }}>
      <div className="row between">
        <h3 style={{ margin: 0 }}><Icon name="task" /> Задание для вас</h3>
        <span className="badge new">адресно</span>
      </div>
      <p style={{ margin: '8px 0 4px' }}><strong>{t.title}</strong> · <span className="muted small">{t.company_name}</span></p>
      <p className="small muted" style={{ margin: 0 }}>{t.recommended_reason}. Ответ обновит актуальность профиля и станет доказательством навыка в подборе.</p>
      <div style={{ marginTop: 10 }}><Link className="btn sm" to="/c/vacancies">Решить <span className="arrow">→</span></Link></div>
    </div>
  )
}

export default function CandidateHome() {
  const nav = useNavigate()
  const profile = useApi<any>('/candidate/profile')
  const history = useApi<any[]>('/candidate/assessments')
  const [err, setErr] = useState('')
  const p = profile.data
  if (!p) return <Pending error={profile.error} cards={3} />

  const inProgress = history.data?.find((a) => a.status === 'in_progress')
  const last = history.data?.find((a) => a.status === 'finished' && a.kind !== 'skill')
  const hasSurvey = (history.data?.length ?? 0) > 0 || p.specialization
  const steps = [
    { title: 'Профиль', done: !!p.full_name },
    { title: 'Опрос и грейд', done: !!hasSurvey },
    { title: p.grade && !p.grade_confirmed ? 'Тест (грейд не подтверждён)' : 'Тест', done: !!p.grade && p.grade_confirmed },
    { title: 'Согласие на публикацию', done: !!p.consent_publication_at },
  ]
  const current = steps.findIndex((s) => !s.done)

  const startSkill = async (skill: string) => {
    setErr('')
    try {
      const r = await api('/candidate/skill-checks', { body: { skill } })
      toast('Проверка навыка началась')
      nav(`/c/test/${r.assessment.id}`)
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const start = async (grade?: string) => {
    setErr('')
    try {
      const r = await api('/candidate/assessments', { body: grade ? { claimed_grade: grade } : {} })
      nav(`/c/test/${r.assessment.id}`)
    } catch (e: any) {
      if (e.status === 422) nav('/c/survey')
      else setErr(e.message)
    }
  }

  const filled = [p.full_name, p.contact_email, p.phone || p.telegram, p.city, p.experience_years, p.declared_skills?.length,
    p.about, p.fsp_id, p.consent_publication_at].filter(Boolean).length
  const completeness = Math.round((filled / 9) * 100)
  const tests = history.data?.filter((a) => a.status === 'finished').length ?? 0
  return (
    <div className="page">
      <PageHead kicker="// кабинет соискателя" title={p.full_name ? `Здравствуйте, ${p.full_name.split(' ')[0]}` : 'Мой путь'}
                aside={<Category spec={p.specialization} grade={p.grade} confirmed={p.grade_confirmed} />}>
        Здесь видно, на каком вы шаге, какая у вас категория и что подтверждено тестом. Чем полнее профиль,
        тем выше вы в выдаче своей категории.
      </PageHead>
      <div className="kpis stagger">
        <Kpi value={completeness} suffix="%" label="заполненность профиля" hint={completeness < 100 ? 'добавьте контакты, стек и ФСП ID' : 'профиль заполнен полностью'} icon="user" color="#402fff" />
        <Kpi value={Object.keys(p.verified_skills ?? {}).length} label="навыков подтверждено" hint={`заявлено в резюме: ${p.declared_skills?.length ?? 0}`} icon="check" color="#0ea5a4" />
        <Kpi value={p.achievements?.length ?? 0} label="результатов ФСП" hint={p.fsp_id ? `ФСП ID ${p.fsp_id}` : 'ФСП ID не привязан'} icon="trophy" color="#ec1d35" />
        <Kpi value={tests} label="попыток тестирования" hint="тесты на грейд и проверки навыков" icon="terminal" color="#f59e0b" />
      </div>
      <div className="card spot">
        <div className="row between">
          <h2>Мой путь</h2>
          {p.is_visible ? <span className="badge ok">Профиль виден работодателям</span> : <span className="badge warn">Профиль скрыт</span>}
        </div>
        <div className="steps">
          {steps.map((s, i) => (
            <div key={s.title} className={`step ${s.done ? 'done' : i === current ? 'current' : ''}`}>
              {s.title}{s.done && ' ✓'}
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 16 }}>
          {current === 0 && <Link className="btn" to="/c/profile">Заполнить профиль</Link>}
          {current === 1 && <Link className="btn" to="/c/survey">Пройти опрос</Link>}
          {current === 2 && !inProgress && <button onClick={() => start()}>{p.grade ? 'Пройти тест на уровень ниже' : 'Начать тест'} <span className="arrow">→</span></button>}
          {current === 2 && !inProgress && p.grade && !p.grade_confirmed && (
            <button className="secondary" onClick={() => nav('/c/survey')}>Выбрать другой грейд</button>
          )}
          {inProgress && <Link className="btn" to={`/c/test/${inProgress.id}`}>Продолжить тест</Link>}
          {current === 3 && <Link className="btn" to="/c/settings">Открыть профиль работодателям</Link>}
        </div>
      </div>

      <ErrorBox error={err} />

      <div className="grid stagger">
        <div className="card spot">
          <h3>Категория</h3>
          <Category spec={p.specialization} grade={p.grade} confirmed={p.grade_confirmed} />
          {p.grade && !p.grade_confirmed && (
            <div className="alert warn small" style={{ marginTop: 12 }}>
              Заявленный грейд тестом не подтверждён. {p.privacy?.show_unconfirmed === false
                ? 'Вы скрыли профиль до успешной пересдачи.'
                : 'Работодатели видят профиль с пометкой «не подтверждён» ниже подтверждённых кандидатов.'}{' '}
              Тест на уровень ниже доступен сразу, повтор этого уровня — через 30 дней.{' '}
              <Link to="/c/settings">Показывать или скрыть</Link>
            </div>
          )}
          {p.grade && (
            <div className="stack small" style={{ marginTop: 12 }}>
              {p.grade_confirmed && <div className="muted">Присвоена {fmtDate(p.grade_assigned_at)}. Сменить грейд можно с {fmtDate(p.next_grade_change_at)}.</div>}
              <SkillChips verified={p.verified_skills} declared={p.declared_skills} />
            </div>
          )}
          {last?.outcome === 'not_confirmed' && (
            <div className="alert info small" style={{ marginTop: 12 }}>
              {last.explanation}
              {last.suggested_grade && (
                <div style={{ marginTop: 8 }}>
                  <button onClick={() => start(last.suggested_grade)}>Тест на {GRADE_TITLES[last.suggested_grade]}</button>
                </div>
              )}
            </div>
          )}
          {p.upgrade_available && (
            <div className="alert ok small" style={{ marginTop: 12 }}>
              Вы справились уверенно — система предлагает отдельный тест на <strong>{GRADE_TITLES[p.upgrade_available]}</strong>.
              Он доступен сразу, без ожидания 90 дней: автоматического повышения нет, грейд меняет только новый тест.
              <div style={{ marginTop: 8 }}><button onClick={() => start(p.upgrade_available)}>Тест на {GRADE_TITLES[p.upgrade_available]} <span className="arrow">→</span></button></div>
            </div>
          )}
        </div>
        <div className="card spot">
          <h3>Достижения ФСП</h3>
          {p.fsp_id ? (
            p.achievements.length ? (
              <div className="stack" style={{ gap: 8 }}>
                {p.achievements.map((a: any, i: number) => (
                  <div key={i} className="row small" style={{ gap: 10, flexWrap: 'nowrap' }}>
                    <span className={`badge ${a.place && a.place <= 3 ? 'ok' : 'neutral'}`} style={{ minWidth: 74, justifyContent: 'center' }}>
                      {a.place ? `${a.place} место` : 'участие'}
                    </span>
                    <span>{a.event_name}</span>
                  </div>
                ))}
                {p.fsp_rank && <div className="small">Спортивный разряд: <strong>{p.fsp_rank}</strong></div>}
                <div className="field-hint">Все соревнования ФСП учитываются одинаково: важны число стартов и результат. Грейд они не меняют.</div>
              </div>
            ) : (
              <p className="muted small">ФСП ID привязан, но истории соревнований пока нет. Профиль ранжируется по результатам теста.</p>
            )
          ) : (
            <div className="stack">
              <p className="muted small" style={{ margin: 0 }}>Привяжите ФСП ID, чтобы достижения автоматически попали в профиль и подняли вас внутри категории.</p>
              <Link className="btn fsp sm" to="/c/settings"><Icon name="key" /> Привязать ФСП ID</Link>
            </div>
          )}
        </div>
      </div>

      {p.grade && <TaskOfWeek />}
      {p.grade && <SkillChecks onStart={startSkill} disabled={!!inProgress} />}

      <div className="card" data-reveal>
        <h3>История тестирования</h3>
        {!history.data?.length ? <p className="muted small">Пока нет попыток.</p> : (
          <table>
            <thead><tr><th>Дата</th><th>Специализация</th><th>Заявлено</th><th>Результат</th><th>θ ± SE</th></tr></thead>
            <tbody>
              {history.data.map((a) => (
                <tr key={a.id}>
                  <td>{fmtDate(a.started_at)}</td>
                  <td>{a.kind === 'skill' ? `Навык: ${a.skill}` : SPEC_TITLES[a.specialization]}</td>
                  <td>{a.kind === 'skill' ? '—' : GRADE_TITLES[a.claimed_grade]}</td>
                  <td>{a.status === 'in_progress' ? <span className="badge">В процессе</span> : <span className={`badge ${OUTCOME[a.outcome]?.[1]}`}>{OUTCOME[a.outcome]?.[0]}</span>}</td>
                  <td>{a.theta.toFixed(2)} ± {a.theta_se.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Tips title="Как подняться в выдаче" items={[
        ['Подтвердите навыки из резюме', 'Короткая проверка на 4–6 заданий превращает «заявлено» в «подтверждено» — такой навык весит в подборе в разы больше.'],
        ['Привяжите ФСП ID', 'Победы и призовые места поднимают вас внутри категории. Грейд они не меняют, но работодатель видит их первыми.'],
        ['Решайте задания работодателей', 'Раздел «Вакансии и задания»: свежий результат повышает актуальность профиля.'],
        ['Откройте профиль', 'Без согласия на публикацию работодатели вас не увидят. Контакты всё равно скрыты до вашего решения.'],
      ]} />
    </div>
  )
}
