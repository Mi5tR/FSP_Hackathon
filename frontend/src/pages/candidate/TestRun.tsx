import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, GRADE_TITLES, SPEC_TITLES } from '../../api'
import { ErrorBox, Icon, Pending, SkillChips, toast } from '../../ui'

function Countdown({ from, limit }: { from: string; limit: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const left = Math.max(0, limit - Math.floor((now - new Date(from + 'Z').getTime()) / 1000))
  const r = 22
  const c = 2 * Math.PI * r
  return (
    <div className={`timer ${left < 20 ? 'low' : ''}`} role="timer" aria-label={`Осталось ${left} секунд`}>
      <svg viewBox="0 0 52 52">
        <circle className="track" cx="26" cy="26" r={r} fill="none" strokeWidth="4" />
        <circle className="val" cx="26" cy="26" r={r} fill="none" strokeWidth="4" strokeDasharray={c} strokeDashoffset={c * (1 - left / limit)} />
      </svg>
      <span>{Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}</span>
    </div>
  )
}

/** Сигналы честности по текущему заданию: уходы с вкладки и попытки скопировать условие (подсказки LLM). */
function useIntegrity() {
  const focus = useRef(0)
  const copies = useRef(0)
  const [notice, setNotice] = useState(0)
  useEffect(() => {
    // Уход на другую вкладку вызывает и blur, и visibilitychange — считаем одно событие
    let last = 0
    const bump = () => {
      const now = Date.now()
      if (now - last < 1000) return
      last = now
      focus.current += 1
      setNotice((n) => n + 1)
    }
    const onHide = () => { if (document.hidden) bump() }
    const onBlur = () => bump()
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('blur', onBlur)
    return () => { document.removeEventListener('visibilitychange', onHide); window.removeEventListener('blur', onBlur) }
  }, [])
  const onCopy = useCallback((e: React.ClipboardEvent | React.MouseEvent) => {
    e.preventDefault()
    copies.current += 1
    toast('Копирование условия отключено во время теста', 'error')
  }, [])
  const take = () => {
    const v = { focus_lost: focus.current, copy_attempts: copies.current }
    focus.current = 0
    copies.current = 0
    return v
  }
  return { onCopy, take, notice }
}

export default function TestRun() {
  const { id } = useParams()
  const [step, setStep] = useState<any>(null)
  const [choice, setChoice] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const integrity = useIntegrity()

  useEffect(() => {
    api(`/candidate/assessments/${id}`).then(setStep).catch((e) => setErr(e.message))
  }, [id])

  const submit = useCallback(async () => {
    if (choice === null || !step?.item) return
    setBusy(true)
    try {
      setStep(await api(`/candidate/assessments/${id}/answer`, { body: { item_id: step.item.item_id, option: choice, ...integrity.take() } }))
      setChoice(null)
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }, [choice, step, id, integrity])

  // Клавиатура: 1–4 выбирают вариант, Enter отправляет ответ
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!step?.item || busy) return
      const n = Number(e.key)
      if (n >= 1 && n <= step.item.options.length) setChoice(n - 1)
      if (e.key === 'Enter' && choice !== null) submit()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, choice, busy, submit])

  if (!step) return <Pending error={err} />
  const a = step.assessment
  const item = step.item

  if (!item) {
    const ok = a.result_grade
    const unconfirmed = a.kind !== 'skill' && !ok
    return (
      <div className="page" style={{ maxWidth: 720 }}>
        <div className="card stack spot" style={{ textAlign: 'center' }}>
          <div className="empty" style={{ padding: '8px 0 0' }}><Icon name={ok || a.kind === 'skill' ? 'trophy' : 'zap'} /></div>
          <h2>{a.kind === 'skill' ? 'Навык проверен' : ok ? 'Категория присвоена' : 'Тест завершён'}</h2>
          {ok && <div><span className="badge ok" style={{ fontSize: 15, padding: '6px 14px', animation: 'pop .5s var(--spring)' }}>{SPEC_TITLES[a.specialization]} · {GRADE_TITLES[a.result_grade]}</span></div>}
          <p>{a.explanation}</p>
          {unconfirmed && (
            <div className="alert warn small" style={{ textAlign: 'left' }}>
              Профиль не скрывается: работодатели видят заявленный грейд с пометкой «не подтверждён», ниже подтверждённых.
              Тест на уровень ниже доступен сразу — попытка не сгорает. Профиль можно скрыть до пересдачи в настройках приватности.
            </div>
          )}
          <p className="small muted">Оценка способности θ = {a.theta.toFixed(2)} ± {a.theta_se.toFixed(2)} по {a.answered} заданиям.</p>
          <div style={{ textAlign: 'left' }}><label>Навыки, проверенные тестом</label><SkillChips verified={a.skills} /></div>
          <div><Link className="btn" to="/c" viewTransition>К моему пути <span className="arrow">→</span></Link></div>
        </div>
      </div>
    )
  }

  const progress = (a.answered / a.max_items) * 100
  return (
    <div className="page" style={{ maxWidth: 780 }}>
      <div className="card">
        <div className="row between" style={{ flexWrap: 'nowrap' }}>
          <div>
            <div className="small muted">{a.kind === 'skill' ? `Проверка навыка: ${a.skill}` : `${SPEC_TITLES[a.specialization]} · тест на ${GRADE_TITLES[a.claimed_grade]}`}</div>
            <div className="mono" style={{ fontWeight: 800, fontSize: 18 }}>Задание {item.number} <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>из {a.max_items} макс.</span></div>
            {a.kind !== 'skill' && (
              <div className="small muted">Общий лимит {a.time_limit_min ?? 20} мин · начато в {new Date(a.started_at + (a.started_at.endsWith('Z') ? '' : 'Z')).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })} · тест закончится раньше, когда точность оценки будет достаточной</div>
            )}
          </div>
          <Countdown key={item.item_id} from={item.presented_at} limit={item.time_limit_s} />
        </div>
        <div className="bar" style={{ margin: '14px 0 18px' }}><div style={{ width: `${progress}%`, animation: 'none' }} /></div>

        <div className="question" key={item.item_id}>
          <div className="small muted">{item.title}</div>
          <div className="no-copy" onCopy={integrity.onCopy} onCut={integrity.onCopy} onContextMenu={integrity.onCopy}>
            <h3 style={{ marginTop: 6 }}>{item.prompt}</h3>
            {item.code && <pre>{item.code}</pre>}
          </div>
          <ErrorBox error={err} />
          <div role="radiogroup" aria-label="Варианты ответа">
            {item.options.map((o: string, i: number) => (
              <button key={i} role="radio" aria-checked={choice === i} className={`option ${choice === i ? 'selected' : ''}`} onClick={() => setChoice(i)}>
                <span className="key">{i + 1}</span>
                <code>{o}</code>
              </button>
            ))}
          </div>
        </div>
        <div className="row between" style={{ marginTop: 8 }}>
          <div className="integrity-note">
            <Icon name="shield" />
            <span>Клавиши 1–{item.options.length} и Enter. Уходы с вкладки и копирование фиксируются как сигнал для работодателя
              {integrity.notice > 0 && <> · <strong style={{ color: 'var(--warn)' }}>зафиксировано: {integrity.notice}</strong></>}.</span>
          </div>
          <button disabled={choice === null || busy} onClick={submit}>{busy ? <span className="spinner" /> : <>Ответить <span className="arrow">→</span></>}</button>
        </div>
      </div>
      <p className="small muted" style={{ textAlign: 'center' }}>Ответ после окончания времени не засчитывается. Правильные ответы не передаются в браузер.</p>
    </div>
  )
}
