import { useState } from 'react'
import { GRADE_TITLES, SPEC_TITLES } from '../../api'
import { Empty, ErrorBox, PageHead, Skeleton, useApi } from '../../ui'
import { CandidateRow, InviteModal } from './shared'

export default function Search() {
  const [spec, setSpec] = useState('backend')
  const [grade, setGrade] = useState('middle')
  const [skills, setSkills] = useState('')
  const [fsp, setFsp] = useState(false)
  const qs = new URLSearchParams({ specialization: spec, grade, limit: '40' })
  skills.split(',').map((s) => s.trim()).filter(Boolean).forEach((s) => qs.append('skills', s))
  if (fsp) qs.set('require_fsp', 'true')
  const res = useApi<any>(`/employer/candidates?${qs}`)
  const [invite, setInvite] = useState<any>(null)

  return (
    <div className="page">
      <PageHead kicker="// поиск" title="Банк кандидатов"
                aside={res.data && <span className="badge">найдено {res.data.total}</span>}>
        Поиск по всем открытым профилям без создания потребности. Карточки обезличены: ФИО и контакты — только после
        согласия кандидата.
      </PageHead>
      <div className="card spot">
        <h2>Фильтры</h2>
        <div className="grid">
          <div><label>Специализация</label>
            <select value={spec} onChange={(e) => setSpec(e.target.value)}>{Object.entries(SPEC_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </div>
          <div><label>Грейд</label>
            <select value={grade} onChange={(e) => setGrade(e.target.value)}>{Object.entries(GRADE_TITLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </div>
          <div><label>Стек (через запятую)</label><input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="python, sql" /></div>
        </div>
        <label className="row" style={{ fontWeight: 400, marginTop: 12 }}>
          <input type="checkbox" checked={fsp} onChange={(e) => setFsp(e.target.checked)} /> Только с достижениями ФСП
        </label>
      </div>
      <ErrorBox error={res.error} />
      {res.data && <p className="small muted">Найдено: {res.data.total}. Категории: {res.data.categories.map((c: any) => `${c.title} (${c.count})`).join(', ')}</p>}
      {res.loading && !res.data && <Skeleton cards={2} />}
      {res.data && !res.data.items.length && <Empty icon="user" title="Никого не нашли">Попробуйте другой грейд или уберите часть стека.</Empty>}
      <div className="stagger" key={qs.toString()}>
        {res.data?.items.map((m: any) => <CandidateRow key={m.candidate.id} m={m} onInvite={setInvite} />)}
      </div>
      {invite && <InviteModal m={invite} onClose={() => setInvite(null)} onSent={() => { setInvite(null); res.reload() }} />}
    </div>
  )
}
