import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, fmtDate, GRADE_TITLES, SPEC_TITLES, STATUS_TITLES } from '../../api'
import { LEVEL_TITLES, RequirementsEditor, ScoringPanel, type Requirement } from '../../match'
import { Empty, ErrorBox, Icon, Pending, Salary, StatusBadge, toast, useApi } from '../../ui'
import { CandidateRow, InviteModal } from './shared'

type Tab = 'matches' | 'settings' | 'shortlist' | 'test' | 'applications'

export default function NeedPage() {
  const { id } = useParams()
  const needs = useApi<any[]>('/employer/needs')
  const need = needs.data?.find((n) => String(n.id) === id)
  const [tab, setTab] = useState<Tab>('matches')
  const [fsp, setFsp] = useState(false)
  const [grade, setGrade] = useState('')
  const [spec, setSpec] = useState('')
  const [version, setVersion] = useState(0)
  const qs = new URLSearchParams({ limit: '30', v: String(version) })
  if (fsp) qs.set('require_fsp', 'true')
  if (grade) qs.set('grade', grade)
  if (spec) qs.set('specialization', spec)
  const matches = useApi<any>(`/employer/needs/${id}/matches?${qs}`)
  const shortlist = useApi<any[]>(tab === 'shortlist' ? `/employer/needs/${id}/shortlist?v=${version}` : null)
  const bp = useApi<any>(tab === 'test' ? `/employer/needs/${id}/test-blueprint?v=${version}` : null)
  const apps = useApi<any[]>(tab === 'applications' ? `/employer/needs/${id}/applications` : null)
  const [invite, setInvite] = useState<any>(null)
  const [reqs, setReqs] = useState<Requirement[]>([])
  const [err, setErr] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [moreCats, setMoreCats] = useState(false)

  useEffect(() => { if (need) setReqs(need.requirements) }, [need])
  // Подборка открыта: следующие новые кандидаты категории будут отмечены как «новые»
  const seenOnce = useRef(false)
  useEffect(() => {
    if (matches.data && !seenOnce.current) {
      seenOnce.current = true
      api(`/employer/needs/${id}/seen`, { body: {} }).catch(() => {})
    }
  }, [matches.data, id])
  const picked = spec && grade ? matches.data?.categories.find((c: any) => c.specialization === spec && c.grade === grade) : null
  const showList = !!picked || showAll

  const refresh = () => { needs.reload(); setVersion((v) => v + 1) }
  const toggleShortlist = async (m: any) => {
    try {
      if (m.shortlisted) await api(`/employer/needs/${id}/shortlist/${m.candidate.id}`, { method: 'DELETE' })
      else await api(`/employer/needs/${id}/shortlist`, { body: { candidate_id: m.candidate.id } })
      toast(m.shortlisted ? 'Убран из шорт-листа' : 'Добавлен в шорт-лист')
      matches.reload()
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const saveRequirements = async () => {
    try {
      await api(`/employer/needs/${id}`, { method: 'PUT', body: { ...need, requirements: reqs } })
      toast('Требования сохранены, подборка пересчитана')
      refresh()
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const setAppStatus = async (aid: number, status: string) => {
    await api(`/employer/applications/${aid}`, { method: 'PATCH', body: { status } })
    apps.reload()
  }

  if (!need) return <Pending error={needs.error} cards={3} />
  const excluded = Object.entries(matches.data?.excluded ?? {}) as [string, number][]
  return (
    <div className="page">
      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>{need.title}</h2>
          <Salary from={need.salary_from} to={need.salary_to} big />
        </div>
        <div className="small muted" style={{ marginBottom: 8 }}>
          {SPEC_TITLES[need.specialization]} · {GRADE_TITLES[need.grade]}
          {need.ats_external_id && <> · <Icon name="link" /> из ATS ({need.ats_external_id})</>}
          {need.new_candidates > 0 && <> · <span className="badge new">+{need.new_candidates} новых в категории</span></>}
        </div>
        <div className="row" style={{ gap: 6 }}>
          {need.requirements.map((r: any) => (
            <span key={r.skill} className={`req ok ${r.importance === 'nice' ? 'nice' : ''}`} title={r.importance === 'must' ? 'обязательно' : 'желательно'}>
              {r.skill} · {LEVEL_TITLES[r.level]}
            </span>
          ))}
        </div>
      </div>

      <div className="tabs">
        {([['matches', 'Подборка'], ['settings', 'Настройки подбора'], ['shortlist', 'Шорт-лист'], ['test', 'Как тестируем кандидатов'],
           ['applications', 'Отклики']] as [Tab, string][]).map(([k, t]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{t}</button>
        ))}
      </div>
      <ErrorBox error={err || matches.error} />

      {tab === 'matches' && matches.data && (
        <>
          {!showList ? (
            <>
              <div className="section-title" style={{ marginTop: 4 }}>
                <h2>Шаг 1. Рекомендованные категории</h2>
                <span className="muted small">категория = специализация + подтверждённый грейд; сначала точное совпадение, затем смежные</span>
              </div>
              <div className="cat-grid stagger">
                {matches.data.categories.filter((c: any) => moreCats || c.fit >= 0.25).map((c: any) => (
                  <button key={c.title} type="button" className="cat-card spot"
                          style={{ '--c': c.fit >= 1 ? 'var(--brand)' : c.fit >= 0.5 ? '#0ea5a4' : '#f59e0b' } as React.CSSProperties}
                          onClick={() => { setSpec(c.specialization); setGrade(c.grade); setShowAll(false) }}>
                    <div className="row between">
                      <span className="cc-title">{c.title}</span>
                      {c.new > 0 && <span className="badge new">+{c.new} новых</span>}
                    </div>
                    <div className="row between" style={{ alignItems: 'flex-end' }}>
                      <span><span className="cc-big">{c.count}</span> <span className="small muted">канд.</span></span>
                      <span className="small muted">лучший — {c.best_percent}%</span>
                    </div>
                    <div className="cc-bar" title={`Средняя релевантность ${Math.round(c.avg_score * 100)}%`}><i style={{ width: `${Math.round(c.avg_score * 100)}%` }} /></div>
                    <div className="cc-meta">
                      <span className="badge neutral">{c.fit >= 1 ? 'точное совпадение' : `смежная · ${Math.round(c.fit * 100)}%`}</span>
                      {c.with_fsp > 0 && <span className="badge fsp">ФСП: {c.with_fsp}</span>}
                      {c.unconfirmed > 0 && <span className="badge warn">не подтв.: {c.unconfirmed}</span>}
                    </div>
                    <span className="small" style={{ color: 'var(--brand-text)' }}>Смотреть кандидатов <span className="arrow">→</span></span>
                  </button>
                ))}
              </div>
              {!moreCats && matches.data.categories.some((c: any) => c.fit < 0.25) && (
                <button className="secondary sm" style={{ marginTop: 12 }} onClick={() => setMoreCats(true)}>
                  Показать дальние категории ({matches.data.categories.filter((c: any) => c.fit < 0.25).length}) — смежные специализации и грейды через ступень
                </button>
              )}
              {!matches.data.categories.length && <Empty icon="inbox" title="Подходящих категорий нет">Ослабьте жёсткие фильтры в настройках подбора.</Empty>}
              <div className="row" style={{ marginTop: 14 }}>
                <button className="secondary" onClick={() => { setShowAll(true); setSpec(''); setGrade('') }}>Показать всех кандидатов подряд ({matches.data.total})</button>
                <span className="small muted">Порядок категорий — по близости к потребности и средней релевантности.</span>
              </div>
            </>
          ) : (
            <>
              <div className="crumbs">
                <button className="secondary sm" onClick={() => { setSpec(''); setGrade(''); setShowAll(false) }}>← Все категории</button>
                <strong>Шаг 2. {picked ? picked.title : 'Все категории'}</strong>
                <span className="badge neutral">найдено {matches.data.total}</span>
              </div>
              <div className="card">
                <div className="row">
                  <label className="row" style={{ fontWeight: 400 }}><input type="checkbox" checked={fsp} onChange={(e) => setFsp(e.target.checked)} /> Только с достижениями ФСП</label>
                  <span className="small muted">Фильтры уточняют выдачу, шорт-лист и категории сохраняются.</span>
                </div>
                {excluded.length > 0 && (
                  <div className="alert info small" style={{ marginTop: 10 }}>
                    Жёсткие фильтры скрыли: {excluded.map(([k, n]) => `${matches.data.excluded_titles[k]} — ${n}`).join('; ')}.
                    {' '}<a href="#" onClick={(e) => { e.preventDefault(); setTab('settings') }}>Изменить</a>
                  </div>
                )}
              </div>
              <p className="small muted">
                Процент — итоговая релевантность (слабый блок нельзя «перекрыть» сильным); «≈ подходят» — откалиброванная
                вероятность, что кандидат релевантен. Внутри категории выше те, у кого сильнее тест и есть результаты ФСП;
                неподтверждённый грейд — ниже подтверждённых, с пунктирной рамкой.
              </p>
              {!matches.data.items.length && <Empty icon="inbox" title="Под эти фильтры никто не подходит">Ослабьте фильтры или выберите другую категорию.</Empty>}
              <div className="stack stagger">
                {matches.data.items.map((m: any) => (
                  <CandidateRow key={m.candidate.id} m={m} onInvite={setInvite} onShortlist={toggleShortlist} />
                ))}
              </div>
            </>
          )}
        </>
      )}

      {tab === 'settings' && (
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))' }}>
          <div className="card stack">
            <h3>Требования к навыкам</h3>
            <RequirementsEditor value={reqs} onChange={setReqs} />
            <div><button onClick={saveRequirements}>Сохранить требования</button></div>
          </div>
          <div className="card">
            <h3>Как считать релевантность</h3>
            <ScoringPanel needId={need.id} value={need.scoring} onSaved={refresh} />
          </div>
        </div>
      )}

      {tab === 'shortlist' && (
        shortlist.data?.length ? shortlist.data.map((m: any) => (
          <CandidateRow key={m.candidate.id} m={m} onInvite={setInvite} />
        )) : <Empty icon="star" title="Шорт-лист пуст">Отмечайте кандидатов звёздочкой в подборке — они сохранятся при смене фильтров.</Empty>
      )}

      {tab === 'test' && bp.data && (
        <div className="card stack">
          <h3>Тест для категории {SPEC_TITLES[need.specialization]} · {GRADE_TITLES[need.grade]}</h3>
          <p className="small">
            Адаптивный тест из {bp.data.min_items}–{bp.data.max_items} заданий. Каждое задание — вариант из параметрического
            семейства: числа, имена и код генерируются заново для каждого кандидата, а сложность семейства откалибрована
            (IRT), поэтому результаты сравнимы. Стек вакансии повышает приоритет релевантных семейств.
          </p>
          <div className="small">
            Покрыто тестом: {bp.data.skills_covered.join(', ') || '—'}
            {Object.keys(bp.data.skills_via).length > 0 && <> · проверяется через навык-родитель: {Object.entries(bp.data.skills_via).map(([a, b]) => `${a} → ${b}`).join(', ')}</>}
            {bp.data.skills_not_in_bank.length > 0 && <> · пока не покрыто банком: {bp.data.skills_not_in_bank.join(', ')}</>}
          </div>
          <table>
            <thead><tr><th>Семейство</th><th>Навык</th><th>Трудность b</th><th>Доля</th><th>Пример варианта</th></tr></thead>
            <tbody>
              {bp.data.families.map((f: any) => (
                <tr key={f.family_id}>
                  <td>{f.title}</td>
                  <td>{f.vacancy_skill ? <strong>{f.skill}</strong> : f.skill}</td>
                  <td>{f.difficulty_b.toFixed(1)}</td>
                  <td>{Math.round(f.share * 100)}%</td>
                  <td className="small">{f.sample.prompt}{f.sample.code && <pre style={{ margin: '4px 0 0', fontSize: 11 }}>{f.sample.code}</pre>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'applications' && (
        apps.data?.length ? apps.data.map((a: any) => (
          <div key={a.id} className="card">
            <div className="row between">
              <strong>{a.candidate.display_name}</strong>
              <div className="row">
                <StatusBadge status={a.status} titles={STATUS_TITLES} />
                <button className="secondary" onClick={() => setAppStatus(a.id, 'invited')}>Пригласить</button>
                <button className="danger" onClick={() => setAppStatus(a.id, 'rejected')}>Отказать</button>
              </div>
            </div>
            <div className="small muted">Отклик от {fmtDate(a.created_at)}</div>
            {a.candidate.contacts && <div className="small">Контакты: {a.candidate.contacts.email}, {a.candidate.contacts.phone}</div>}
          </div>
        )) : <div className="card muted">{need.is_published ? 'Откликов пока нет.' : 'Потребность не опубликована как вакансия, откликов нет.'}</div>
      )}

      {invite && <InviteModal m={invite} need={need} onClose={() => setInvite(null)} onSent={() => { setInvite(null); matches.reload() }} />}
    </div>
  )
}
