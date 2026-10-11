import { useEffect, useState } from 'react'
import { api, fmtDate } from '../../api'
import { FspIdButton } from '../../fspid'
import { ErrorBox, PageHead, Pending, Tips, toast, useApi } from '../../ui'

const PRIVACY: [string, string][] = [
  ['show_city', 'Показывать город'],
  ['show_experience', 'Показывать стаж'],
  ['show_about', 'Показывать раздел «О себе»'],
  ['show_fsp', 'Показывать достижения ФСП'],
  ['show_unconfirmed', 'Показывать профиль, пока грейд не подтверждён тестом (с пометкой «не подтверждён»)'],
  ['hide_below_expectation', 'Не получать приглашения с вилкой ниже моих зарплатных ожиданий'],
]
const DEFAULTS: Record<string, boolean> = { hide_below_expectation: false }

export default function Settings() {
  const { data, error, setData } = useApi<any>('/candidate/profile')
  const [privacy, setPrivacy] = useState<any>({})
  const [consent, setConsent] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!data) return
    setPrivacy(data.privacy)
    setConsent(!!data.consent_publication_at)
  }, [data])
  if (!data) return <Pending error={error} />

  const savePrivacy = async () => {
    setErr('')
    try {
      setData(await api('/candidate/privacy', { method: 'PUT', body: { ...privacy, consent_publication: consent } }))
      toast(consent ? 'Профиль открыт работодателям' : 'Настройки сохранены')
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const unlink = async () => {
    setData(await api('/candidate/fsp/link', { method: 'DELETE' }))
    toast('ФСП ID отвязан')
  }

  return (
    <div className="page">
      <PageHead kicker="// данные и согласия" title="Приватность и ФСП ID">
        Вы решаете, что видят работодатели. Согласия можно отозвать в любой момент — по 152-ФЗ.
      </PageHead>
      <div className="with-aside">
      <div className="stack stagger">
      <div className="card stack spot">
        <h2>Приватность</h2>
        <p className="small muted">Контакты (ФИО, телефон, email, Telegram) работодатель видит только после того, как вы примете приглашение или откликнетесь сами. Доступ можно отозвать в карточке приглашения.</p>
        <ErrorBox error={err} />
        {PRIVACY.map(([k, t]) => (
          <label key={k} className="row" style={{ fontWeight: 400 }}>
            <input type="checkbox" checked={privacy[k] ?? DEFAULTS[k] ?? true} onChange={(e) => setPrivacy({ ...privacy, [k]: e.target.checked })} /> {t}
          </label>
        ))}
        <label className="row" style={{ fontWeight: 600 }}>
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          Согласен на публикацию обезличенного профиля для работодателей
        </label>
        {data.minor_blocked && <div className="alert warn small">До 18 лет профиль публикуется только с согласия законного представителя — заполните его в разделе «Профиль».</div>}
        <div className="small muted">Согласие на обработку ПДн дано {fmtDate(data.consent_processing_at)}. Отозвать согласие на публикацию можно в любой момент.</div>
        <div><button onClick={savePrivacy}>Сохранить</button></div>
      </div>

      <div className="card stack spot">
        <h2>ФСП ID</h2>
        {data.fsp_id ? (
          <>
            <div className="row">Привязан: <span className="badge fsp">{data.fsp_id}</span></div>
            <div className="small muted">
              {data.achievements.length ? `Загружено достижений: ${data.achievements.length}` : 'История соревнований в реестре ФСП пока пуста — это нормально, профиль ранжируется по тесту.'}
            </div>
            <div className="row">
              <FspIdButton label="Обновить из ФСП ID" />
              <button className="secondary" onClick={unlink}>Отвязать</button>
            </div>
          </>
        ) : (
          <>
            <p className="small muted" style={{ margin: 0 }}>
              Привязка идёт через вход в ФСП ID (Keycloak, OpenID Connect): идентификатор берётся из токена, поэтому
              привязать чужой ID нельзя. Достижения подтягиваются из реестра ФСП автоматически и поднимают вас внутри
              категории; грейд они не меняют.
            </p>
            <FspIdButton label="Привязать ФСП ID" />
          </>
        )}
      </div>
      </div>
      <Tips title="Как устроена приватность" items={[
        ['Обезличенный профиль', 'Без согласия на публикацию вас нет в выдаче. С согласием — есть, но без ФИО и контактов.'],
        ['ФСП ID', 'ID берётся из токена входа, поэтому чужой профиль привязать нельзя. Достижения импортируются из реестра.'],
        ['Отзыв контактов', 'Принятое приглашение можно «откатить»: работодатель снова увидит только обезличенную карточку.'],
        ['До 18 лет', 'Публикация — только с согласием законного представителя, работодатель видит пометку «лёгкий труд».'],
      ]} />
      </div>
    </div>
  )
}
