import { useEffect, useState } from 'react'
import { EN_DICT } from './i18n-en'

/**
 * Переключение языка интерфейса (RU / EN).
 *
 * Исходный текст интерфейса и ответов API — русский. В режиме EN работает переводчик DOM:
 * MutationObserver ловит каждый появившийся или изменившийся текстовый узел (и атрибуты
 * placeholder / title / aria-label) и переводит его по словарю. Сначала ищется вся строка
 * целиком, затем — известные фразы внутри неё (так переводятся динамические строки вроде
 * «Найдено: 12» и объяснения подборки с бэкенда). Пользовательский ввод (поля форм) не трогается.
 * При возврате на RU приложение перемонтируется и показывает исходный текст.
 */
export type Lang = 'ru' | 'en'
const KEY = 'fsp_lang'
const EVENT = 'fsp-lang'

export function getLang(): Lang {
  try {
    return localStorage.getItem(KEY) === 'en' ? 'en' : 'ru'
  } catch {
    return 'ru'
  }
}

export function setLang(l: Lang) {
  try {
    localStorage.setItem(KEY, l)
  } catch { /* приватный режим: язык живёт до перезагрузки */ }
  document.documentElement.lang = l
  if (l === 'en') startTranslator()
  else stopTranslator()
  window.dispatchEvent(new Event(EVENT))
}

export function useLang(): Lang {
  const [l, setL] = useState<Lang>(getLang())
  useEffect(() => {
    const on = () => setL(getLang())
    window.addEventListener(EVENT, on)
    return () => window.removeEventListener(EVENT, on)
  }, [])
  return l
}

export function t(s: string): string {
  return getLang() === 'en' ? translate(s) : s
}

// ------------------------------------------------------------------ переводчик
const CYR = /[А-Яа-яЁё]/
const norm = (s: string) => s.replace(/\s+/g, ' ').trim()
let DICT: Record<string, string> | null = null
let PHRASES: RegExp | null = null
const cache = new Map<string, string>()

function dict(): Record<string, string> {
  if (!DICT) {
    DICT = {}
    for (const [k, v] of Object.entries({ ...EN_DICT, ...EN })) DICT[norm(k)] = v
    // Фразы внутри строк: только от 3 символов (короткие «по», «из» ломали бы названия и имена).
    // Граница слова проверяется только там, где фраза начинается или кончается буквой.
    const L = '[А-Яа-яЁёA-Za-z]'
    const keys = Object.keys(DICT).filter((k) => k.length >= 3).sort((a, b) => b.length - a.length)
    const parts = keys.map((k) => {
      const e = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      return (/^[А-Яа-яЁёA-Za-z]/.test(k) ? `(?<!${L})` : '') + e + (/[А-Яа-яЁёA-Za-z]$/.test(k) ? `(?!${L})` : '')
    })
    PHRASES = new RegExp(parts.join('|'), 'g')
  }
  return DICT
}

/** Перевод строки: целиком, затем без хвостовой пунктуации, затем по известным фразам внутри. */
export function translate(text: string): string {
  if (!text || !CYR.test(text)) return text
  const hit = cache.get(text)
  if (hit !== undefined) return hit
  const d = dict()
  const lead = text.match(/^\s*/)![0]
  const trail = text.match(/\s*$/)![0]
  const core = norm(text)
  let out = d[core]
  if (out === undefined) {
    const m = core.match(/^(.*?)([\s.,:;!?…·—\-()«»"“”]*)$/)!
    if (m[1] && d[m[1]] !== undefined) out = d[m[1]] + m[2]
  }
  if (out === undefined) {
    const cyr = (x: string) => (x.match(/[А-Яа-яЁё]/g) || []).length
    const partial = core.replace(/(\d%?)\s+из\s+(\d)/g, '$1 of $2').replace(/(\d)\s*г\./g, '$1 yrs').replace(PHRASES!, (p) => d[p] ?? p)
    // Если почти весь текст остался русским — это данные (имена, названия, тексты заданий), их не трогаем
    out = cyr(partial) > cyr(core) * 0.8 ? core : partial
  }
  const res = lead + out + trail
  cache.set(text, res)
  return res
}

const ATTRS = ['placeholder', 'title', 'aria-label']
const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'NOSCRIPT'])
const done = new WeakMap<Node, string>()
let observer: MutationObserver | null = null

function translateText(n: Text) {
  const cur = n.data
  if (done.get(n) === cur || !CYR.test(cur)) return
  const p = n.parentElement
  if (!p || SKIP.has(p.tagName) || p.closest('[translate="no"]')) return
  const tr = translate(cur)
  done.set(n, tr)
  if (tr !== cur) n.data = tr
}

function translateAttrs(el: Element) {
  if (el.closest('[translate="no"]')) return
  for (const a of ATTRS) {
    const v = el.getAttribute(a)
    if (v && CYR.test(v)) el.setAttribute(a, translate(v))
  }
}

function walk(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) return translateText(root as Text)
  if (root.nodeType !== Node.ELEMENT_NODE) return
  const el = root as Element
  if (SKIP.has(el.tagName)) return
  translateAttrs(el)
  el.querySelectorAll('[placeholder],[title],[aria-label]').forEach(translateAttrs)
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  for (let n = w.nextNode(); n; n = w.nextNode()) translateText(n as Text)
}

export function startTranslator() {
  if (observer) return
  walk(document.body)
  document.title = translate(document.title)
  observer = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'characterData') translateText(m.target as Text)
      else if (m.type === 'attributes') translateAttrs(m.target as Element)
      else m.addedNodes.forEach(walk)
    }
  })
  observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS })
}

export function stopTranslator() {
  observer?.disconnect()
  observer = null
}

/** Включить переводчик при загрузке, если язык уже выбран. */
export function initLang() {
  document.documentElement.lang = getLang()
  if (getLang() === 'en') startTranslator()
}

const EN: Record<string, string> = {
  // меню и шапка
  'Мой путь': 'My path', 'шаги, категория, история теста': 'steps, category, test history',
  'Приглашения': 'Invitations', 'предложения и переписка': 'offers and chat',
  'Вакансии и задания': 'Jobs & tasks', 'отклики и короткие задачи': 'applications and short tasks',
  'Профиль': 'Profile', 'резюме, стек, PDF-профиль': 'resume, stack, PDF profile',
  'Приватность и ФСП': 'Privacy & FSP', 'согласия, ФСП ID': 'consents, FSP ID',
  'Потребности': 'Hiring needs', 'кого ищем, новые кандидаты': 'who we need, new candidates',
  'Банк кандидатов': 'Talent pool', 'поиск по категориям': 'search by category',
  'статусы и переписка': 'statuses and chat', 'Задания': 'Tasks', 'регулярные задачи и оценки': 'regular tasks and ratings',
  'Компания': 'Company', 'доверие и ATS Huntflow': 'trust and Huntflow ATS',
  'О платформе': 'About', 'как это работает': 'how it works', 'Вход': 'Sign in', 'email, ФСП ID или демо': 'email, FSP ID or demo',
  'Я ищу работу': "I'm looking for a job", 'регистрация соискателя': 'candidate sign-up',
  'Я ищу специалистов': "I'm hiring", 'регистрация работодателя': 'employer sign-up',
  'Выйти': 'Sign out', 'Войти': 'Sign in', 'соискатель': 'candidate', 'работодатель': 'employer',
  'Разделы': 'Sections', 'Меню': 'Menu',
  // главная
  'Федерация спортивного программирования': 'Russian Federation of Sport Programming',
  'Работодатель сам находит вас — ': 'Employers find you — ',
  'по подтверждённым навыкам': 'by verified skills',
  'Пройдите адаптивный тест по специализации и получите категорию. Работодатели видят категорию, результаты тестов и достижения ФСП и присылают приглашение сразу с вилкой зарплаты. Контакты раскрываются только после вашего согласия.':
    'Take an adaptive test in your specialization and get a category. Employers see the category, test results and FSP achievements and send an invitation with the salary range up front. Your contacts are revealed only after you agree.',
  'адаптивных заданий': 'adaptive items', 'специализаций': 'specializations', 'для соискателя': 'for candidates',
  'кандидатов в банке': 'candidates in the pool', 'с присвоенной категорией': 'with an assigned category',
  'участников ФСП': 'FSP participants', 'открытых вакансий': 'open jobs', 'семейств заданий': 'item families',
  'каждый вариант генерируется заново': 'every variant is generated anew',
  'Как это работает': 'How it works', 'обратная механика: не вы рассылаете резюме, а вас приглашают': 'reverse hiring: you do not send resumes, you get invited',
  'Опрос и тест': 'Survey and test', 'Категория': 'Category', 'Приглашение': 'Invitation',
  'Вы сами выбираете грейд, адаптивный тест его подтверждает. Задания генерируются заново для каждого: ответы не «утекают», сложность выровнена.':
    'You choose your grade, the adaptive test confirms it. Items are generated anew for everyone: answers do not leak, difficulty is equated.',
  'Например, «Backend · Middle». Грейд даёт только тест. Достижения ФСП поднимают вас внутри категории, но не меняют грейд.':
    'For example, “Backend · Middle”. Only the test assigns the grade. FSP achievements lift you within the category but never change the grade.',
  'Работодатель пишет первым: позиция, вилка до вычета НДФЛ, способ связи. Можно переписываться, контакты открываются только после вашего согласия.':
    'The employer writes first: position, gross salary range, contact method. You can chat; contacts open only after your consent.',
  'Путь соискателя': 'Candidate path', 'Путь работодателя': 'Employer path', 'начать →': 'start →',
  'Специализации': 'Specializations', 'тест проверяет ключевые навыки каждой специализации': 'the test checks key skills of each specialization',
  'Почему этому можно доверять': 'Why you can trust it', 'механика, а не обещания': 'mechanics, not promises',
  'Частые вопросы': 'FAQ', 'Пройдите тест один раз — дальше работодатели пишут сами': 'Take the test once — then employers write to you',
  'Вход через ФСП ID': 'Sign in with FSP ID', 'Объяснимый подбор': 'Explainable matching', 'Честный тест': 'Fair test',
  'Согласие на обработку ПДн, обезличенные карточки, отзыв доступа к контактам в один клик.': 'Personal data consent, anonymized cards, one-click contact revocation.',
  'Достижения подтягиваются из реестра ФСП, а не вписываются вручную.': 'Achievements come from the FSP registry, not typed in by hand.',
  'Работодатель видит, почему кандидат в выдаче: блоки, навыки, флаги.': 'Employers see why a candidate is shown: blocks, skills, flags.',
  'Уникальные варианты заданий, контроль времени и сигналы честности прохождения.': 'Unique item variants, time control and integrity signals.',
  // подвал
  'Механика': 'Mechanics', 'Доверие': 'Trust', 'Для проверки': 'For reviewers',
  // заголовки разделов
  '// кабинет соискателя': '// candidate space', '// кабинет работодателя': '// employer space',
  'Потребности и подбор': 'Hiring needs and matching', 'Приглашения от работодателей': 'Invitations from employers',
  'Профиль и резюме': 'Profile and resume', 'Приватность и ФСП ID': 'Privacy and FSP ID',
  'Регулярные задания': 'Regular tasks', 'Профиль компании, доверие и ATS': 'Company profile, trust and ATS',
  'Опрос: направление, специализация, грейд': 'Survey: field, specialization, grade',
  '// шаг 1 из 3 · опрос': '// step 1 of 3 · survey', '// входящие': '// inbox', '// исходящие': '// outbox',
  '// резюме': '// resume', '// данные и согласия': '// data and consents', '// о компании': '// about company',
  '// оценка навыков': '// skill assessment', '// возможности': '// opportunities',
  'Как подняться в выдаче': 'How to rank higher', 'Как устроен путь': 'How the path works',
  'Что повышает доверие': 'What builds trust', 'Как получить сильную подборку': 'How to get a strong shortlist',
}
