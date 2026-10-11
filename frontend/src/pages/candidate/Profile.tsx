import { useEffect, useState } from 'react'
import { api, download } from '../../api'
import { ErrorBox, PageHead, Pending, Tips, toast, useApi } from '../../ui'

const FIELDS: [string, string, string?][] = [
  ['full_name', 'ФИО'],
  ['contact_email', 'Email для связи', 'email'],
  ['phone', 'Телефон'],
  ['telegram', 'Telegram'],
  ['city', 'Город'],
  ['experience_years', 'Стаж, лет', 'number'],
  ['salary_expectation', 'Ожидания по зарплате, ₽ до вычета НДФЛ (работодатель видит только «в вилке / выше»)', 'number'],
]

export default function CandidateProfile() {
  const { data, error, setData } = useApi<any>('/candidate/profile')
  const [form, setForm] = useState<any>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (data) setForm({ ...data, declared_skills: data.declared_skills.join(', '), soft_skills: data.soft_skills.join(', '),
                        guardian_consent: !!data.guardian_consent_at })
  }, [data])
  if (!form) return <Pending error={error} />

  const set = (k: string, v: any) => setForm({ ...form, [k]: v })
  const age = form.birth_date ? Math.floor((Date.now() - new Date(form.birth_date).getTime()) / (365.25 * 864e5)) : null
  const minor = age !== null && age < 18
  const save = async () => {
    setErr('')
    try {
      const split = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)
      const body: any = {
        ...Object.fromEntries(FIELDS.map(([k, , t]) => [k, t === 'number' ? (form[k] === '' || form[k] === null ? null : Number(form[k])) : form[k] || null])),
        declared_skills: split(form.declared_skills),
        soft_skills: split(form.soft_skills),
        about: form.about,
        work_format: form.work_format,
        open_to_offers: form.open_to_offers,
        birth_date: form.birth_date || null,
        guardian_name: form.guardian_name || null,
        guardian_contact: form.guardian_contact || null,
        ...(minor ? { guardian_consent: !!form.guardian_consent } : {}),
      }
      setData(await api('/candidate/profile', { method: 'PUT', body }))
      toast('Профиль сохранён')
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const upload = async (file: File) => {
    setErr('')
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await api('/candidate/resume/parse', { form: fd })
      const merged = { ...form }
      for (const k of ['full_name', 'contact_email', 'phone', 'telegram', 'experience_years']) if (r[k]) merged[k] = r[k]
      const skills = [...(r.declared_skills ?? []), ...(r.suggested_skills ?? []).map((x: any) => x.skill)]
      if (skills.length) merged.declared_skills = skills.join(', ')
      if (r.soft_skills?.length) merged.soft_skills = r.soft_skills.join(', ')
      setForm(merged)
      const fuzzy = (r.suggested_skills ?? []).map((x: any) => `${x.matched} → ${x.title}`)
      const spec = r.specialization_ml?.[0]
      toast(`Поля распознаны из PDF — проверьте и сохраните.${fuzzy.length ? ` По сходству: ${fuzzy.join(', ')}.` : ''}${spec ? ` ML: вероятно, ${spec.title} (${Math.round(spec.probability * 100)}%).` : ''}`)
    } catch (e: any) {
      setErr(e.message)
    }
  }

  return (
    <div className="page">
      <PageHead kicker="// резюме" title="Профиль и резюме">
        Самоописание дополняет карточку для работодателя. Категорию оно не меняет — её присваивает только тест.
        Готовый профиль можно скачать стандартизированным PDF.
      </PageHead>
      <div className="with-aside">
      <div className="card stack spot">
        <div className="row between">
          <h2>Профиль и резюме</h2>
          <div className="row" style={{ gap: 8 }}>
          <button className="secondary" onClick={() => download('/candidate/profile/pdf', 'fsp-profile.pdf').then(() => toast('PDF-профиль сформирован')).catch((e) => toast(e.message, 'error'))}>
            Скачать PDF-профиль
          </button>
          <label className="btn secondary" style={{ margin: 0 }}>
            Распознать из PDF
            <input type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          </div>
        </div>
        <div className="alert info small">
          Самоописание дополняет карточку, но не определяет категорию: категория присваивается только по итогам теста.
        </div>
        <ErrorBox error={err} />
        <div className="grid">
          {FIELDS.map(([k, title, type]) => (
            <div key={k}><label>{title}</label><input type={type ?? 'text'} value={form[k] ?? ''} onChange={(e) => set(k, e.target.value)} /></div>
          ))}
          <div>
            <label>Формат работы</label>
            <select value={form.work_format} onChange={(e) => set('work_format', e.target.value)}>
              <option value="any">Любой</option><option value="remote">Удалённо</option>
              <option value="hybrid">Гибрид</option><option value="office">Офис</option>
            </select>
          </div>
        </div>
        <div className="card flat stack" style={{ margin: 0 }}>
          <div className="grid">
            <div>
              <label htmlFor="birth">Дата рождения</label>
              <input id="birth" type="date" value={form.birth_date ?? ''} onChange={(e) => set('birth_date', e.target.value)} />
              <div className="field-hint">Нужна для работы с участниками 15–17 лет. Работодатель видит только отметку «до 18».</div>
            </div>
          </div>
          {age !== null && age < 15 && <div className="alert error small">Публикация профиля доступна с 15 лет. Тест пройти можно — результат сохранится.</div>}
          {minor && age !== null && age >= 15 && (
            <div className="stack">
              <div className="alert warn small">
                Вам {age}: по ст. 63 ТК РФ возможен только лёгкий труд, а профиль публикуется с согласия законного представителя на обработку ПДн (152-ФЗ).
              </div>
              <div className="grid">
                <div><label>ФИО законного представителя</label><input value={form.guardian_name ?? ''} onChange={(e) => set('guardian_name', e.target.value)} /></div>
                <div><label>Контакт представителя</label><input value={form.guardian_contact ?? ''} onChange={(e) => set('guardian_contact', e.target.value)} placeholder="телефон или email" /></div>
              </div>
              <label className="row" style={{ fontWeight: 400 }}>
                <input type="checkbox" checked={!!form.guardian_consent} onChange={(e) => set('guardian_consent', e.target.checked)} />
                Законный представитель дал согласие на обработку и публикацию моих персональных данных
              </label>
            </div>
          )}
        </div>
        <div><label>Стек (через запятую)</label><input value={form.declared_skills} onChange={(e) => set('declared_skills', e.target.value)} /></div>
        <div><label>Софт-скиллы</label><input value={form.soft_skills} onChange={(e) => set('soft_skills', e.target.value)} /></div>
        <div><label>О себе</label><textarea value={form.about} onChange={(e) => set('about', e.target.value)} /></div>
        <label className="row" style={{ fontWeight: 400 }}>
          <input type="checkbox" checked={form.open_to_offers} onChange={(e) => set('open_to_offers', e.target.checked)} /> Открыт к предложениям
        </label>
        <button onClick={save}>Сохранить</button>
      </div>
      <Tips title="Что видит работодатель" items={[
        ['До согласия', '«Кандидат #N», категория, подтверждённые навыки, ФСП, город и стаж — если не скрыты в приватности.'],
        ['После согласия', 'ФИО, email, телефон и Telegram — только той компании, чьё приглашение вы приняли.'],
        ['Ожидания по зарплате', 'Сама сумма не показывается: работодатель видит лишь «в вилке» или «выше примерно на X%».'],
        ['PDF-профиль', 'Единый шаблон для всех кандидатов: удобно приложить к отклику или отправить рекрутеру.'],
      ]} />
      </div>
    </div>
  )
}
