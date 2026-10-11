import { useEffect, useState } from 'react'
import { api } from './api'
import { Ring, useApi } from './ui'

export type Requirement = { skill: string; importance: 'must' | 'nice'; level: 'basic' | 'confident' | 'expert'; title?: string }
export type Block = { key: string; title: string; score: number; weight: number; reason: string }
export type ReqResult = {
  skill: string; title: string; importance: string; level: string; coverage: number
  confidence: number; source: string | null; reason: string; testable: boolean; status: string
}
export type Flag = { severity: string; text: string }

export const LEVEL_TITLES: Record<string, string> = { basic: 'базовый', confident: 'уверенный', expert: 'эксперт' }
const STATUS_TITLES: Record<string, string> = { ok: 'подтверждён', unverified: 'не подтверждён напрямую', failed: 'не закрыт' }
const SOURCE_TITLES: Record<string, string> = { test: 'тест', microtask: 'задания', fsp: 'ФСП', declared: 'резюме' }

const pct = (x: number) => `${Math.round(x * 100)}%`
const tone = (x: number) => (x >= 0.7 ? 'ok' : x >= 0.45 ? 'warn' : 'bad')

export function ScoreHeadline({ percent, probability, confidence }: { percent: number; probability?: number | null; confidence?: number }) {
  return (
    <div title="Итоговая релевантность" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <Ring percent={percent} />
      <div className="score-meta">
        {probability != null && <>≈ {Math.round(probability * 100)}% подходят</>}
        {probability != null && confidence != null && <br />}
        {confidence != null && <>уверенность {pct(confidence)}</>}
      </div>
    </div>
  )
}

/** Разбивка соответствия: блоки, требования, флаги. Используется у работодателя и в приглашении кандидата. */
export function MatchBreakdown({ blocks, requirements, flags, compact }: { blocks: Block[]; requirements: ReqResult[]; flags: Flag[]; compact?: boolean }) {
  return (
    <div className="stack">
      <div className="blocks stagger">
        {blocks.map((b) => (
          <div className="block" key={b.key} title={b.reason}>
            <div className="t"><span>{b.title}</span>{b.key !== 'fsp' && <span>вес {b.weight.toFixed(2)}</span>}</div>
            <div className="v">{b.key === 'fsp' && b.score === 0 ? '—' : pct(b.score)}</div>
            <div className={`bar ${b.key === 'fsp' ? '' : tone(b.score)}`}><div style={{ width: pct(b.score) }} /></div>
            {!compact && <div className="small muted" style={{ marginTop: 4 }}>{b.reason}</div>}
          </div>
        ))}
      </div>
      {requirements.length > 0 && (
        <div>
          <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Требования</div>
          <div className="row" style={{ gap: 6 }}>
            {requirements.map((r) => (
              <span key={r.skill} className={`req ${r.status} ${r.importance === 'nice' ? 'nice' : ''}`}
                    title={`${r.importance === 'must' ? 'Обязательно' : 'Желательно'}, ${LEVEL_TITLES[r.level]} — ${STATUS_TITLES[r.status]}. ${r.reason}`}>
                {r.title} {pct(r.coverage)}
                {r.source && <span style={{ fontWeight: 400, opacity: 0.8 }}>· {SOURCE_TITLES[r.source]}</span>}
              </span>
            ))}
          </div>
          {!compact && (
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Навык</th><th>Требование</th><th>Покрытие</th><th>Статус</th><th>Откуда</th></tr></thead>
              <tbody>
                {requirements.map((r) => (
                  <tr key={r.skill}>
                    <td>{r.title}</td>
                    <td className="small">{r.importance === 'must' ? 'обязательно' : 'желательно'}, {LEVEL_TITLES[r.level]}</td>
                    <td><div className={`bar ${tone(r.coverage)}`} style={{ width: 80 }}><div style={{ width: pct(r.coverage) }} /></div> <span className="small">{pct(r.coverage)}</span></td>
                    <td><span className={`req ${r.status}`}>{STATUS_TITLES[r.status]}</span></td>
                    <td className="small muted">{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {flags.length > 0 && (
        <div>{flags.map((f, i) => <div key={i} className={`flag ${f.severity}`}>{f.text}</div>)}</div>
      )}
    </div>
  )
}

export function RequirementsEditor({ value, onChange }: { value: Requirement[]; onChange: (v: Requirement[]) => void }) {
  const catalog = useApi<any>('/catalog')
  const [add, setAdd] = useState('')
  const skills: any[] = catalog.data?.skills ?? []
  const title = (code: string) => skills.find((s) => s.code === code)?.title ?? code
  const set = (i: number, patch: Partial<Requirement>) => onChange(value.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const used = new Set(value.map((r) => r.skill))
  return (
    <div className="stack">
      {value.length === 0 && <div className="small muted">Требования к стеку не заданы.</div>}
      {value.map((r, i) => (
        <div key={r.skill} className="row" style={{ gap: 8 }}>
          <strong style={{ minWidth: 150 }}>{title(r.skill)}</strong>
          <div className="seg">
            <button type="button" className={r.importance === 'must' ? 'on' : ''} onClick={() => set(i, { importance: 'must' })}>обязательно</button>
            <button type="button" className={r.importance === 'nice' ? 'on' : ''} onClick={() => set(i, { importance: 'nice' })}>желательно</button>
          </div>
          <div className="seg">
            {(['basic', 'confident', 'expert'] as const).map((l) => (
              <button type="button" key={l} className={r.level === l ? 'on' : ''} onClick={() => set(i, { level: l })}>{LEVEL_TITLES[l]}</button>
            ))}
          </div>
          {!skills.find((s) => s.code === r.skill)?.testable_as && <span className="small muted" title="В банке заданий нет проверки этого навыка">нет теста</span>}
          <button type="button" className="secondary sm" aria-label="Убрать навык" onClick={() => onChange(value.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="row" style={{ gap: 8 }}>
        <select value={add} onChange={(e) => setAdd(e.target.value)} style={{ maxWidth: 280 }}>
          <option value="">Добавить навык…</option>
          {skills.filter((s) => !used.has(s.code)).map((s) => (
            <option key={s.code} value={s.code}>{s.parent ? `  ${s.title} (${title(s.parent)})` : s.title}</option>
          ))}
        </select>
        <button type="button" className="secondary" disabled={!add}
                onClick={() => { onChange([...value, { skill: add, importance: 'must', level: 'confident' }]); setAdd('') }}>Добавить</button>
      </div>
    </div>
  )
}

const SLIDERS: [string, string, number, number, number][] = [
  ['strictness', 'Строгость', -3, 1, 0.25],
  ['fsp_bonus', 'Бонус ФСП', 0, 0.5, 0.05],
  ['nice_weight', 'Вес «желательно»', 0, 1, 0.1],
  ['must_threshold', 'Порог must-have', 0, 1, 0.05],
  ['must_penalty', 'Штраф за провал must', 0, 1, 0.05],
  ['unverified_penalty', 'Штраф «не подтверждён»', 0, 1, 0.05],
  ['confidence_weight', 'Учёт уверенности (α)', 0, 2, 0.1],
]

/** Настройки скоринга потребности: веса блоков, строгость, пороги и жёсткие фильтры. */
export function ScoringPanel({ needId, value, onSaved }: { needId: number; value: any; onSaved: () => void }) {
  const meta = useApi<any>('/employer/scoring/defaults')
  const [cfg, setCfg] = useState<any>(value)
  const [busy, setBusy] = useState(false)
  useEffect(() => setCfg(value), [value])
  if (!meta.data || !cfg) return null
  const m = meta.data
  const save = async (next = cfg) => {
    setBusy(true)
    await api(`/employer/needs/${needId}/scoring`, { method: 'PUT', body: next })
    setBusy(false)
    onSaved()
  }
  const totalW = Object.values(cfg.weights as Record<string, number>).reduce((a, b) => a + b, 0) || 1
  const strictLabel = cfg.strictness >= 0.75 ? 'компенсаторно (сумма)' : cfg.strictness > -0.25 ? 'сбалансированно' : 'строго (к минимуму)'
  return (
    <div className="stack">
      <div>
        <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Веса блоков (доля в итоге)</div>
        {Object.entries(cfg.weights as Record<string, number>).map(([k, v]) => (
          <div className="slider-row" key={k}>
            <label style={{ margin: 0, fontWeight: 400 }}>{m.blocks[k]}</label>
            <input type="range" min={0} max={1} step={0.05} value={v}
                   onChange={(e) => setCfg({ ...cfg, weights: { ...cfg.weights, [k]: Number(e.target.value) } })} />
            <span className="val">{Math.round((v / totalW) * 100)}%</span>
          </div>
        ))}
      </div>
      <div>
        <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Логика агрегации</div>
        {SLIDERS.map(([k, t, min, max, step]) => (
          <div className="slider-row" key={k} title={m.help[k]}>
            <label style={{ margin: 0, fontWeight: 400 }}>{t}</label>
            <input type="range" min={min} max={max} step={step} value={cfg[k]} onChange={(e) => setCfg({ ...cfg, [k]: Number(e.target.value) })} />
            <span className="val">{cfg[k].toFixed(2)}</span>
          </div>
        ))}
        <div className="small muted">Строгость: {strictLabel}. {m.help.strictness}</div>
      </div>
      <div>
        <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Жёсткие фильтры (по умолчанию всё мягкое — кандидат остаётся с флагом)</div>
        <div className="row">
          {Object.entries(m.hard_filters as Record<string, string>).map(([k, t]) => (
            <label key={k} className="row" style={{ fontWeight: 400, margin: 0 }}>
              <input type="checkbox" checked={!!cfg.hard[k]} onChange={(e) => setCfg({ ...cfg, hard: { ...cfg.hard, [k]: e.target.checked } })} />
              исключать: {t}
            </label>
          ))}
        </div>
      </div>
      <div className="row">
        <button onClick={() => save()} disabled={busy}>Применить</button>
        <button className="secondary" onClick={() => { setCfg(m.defaults); save(m.defaults) }} disabled={busy}>Сбросить по умолчанию</button>
        <span className="small muted">Значения по умолчанию выбраны по результатам валидации. Шорт-лист при изменении сохраняется.</span>
      </div>
    </div>
  )
}
