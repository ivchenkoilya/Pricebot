import { useEffect } from 'react'
import { hasTelegramAuth } from './api'

const EXACT: Record<string, string> = {
  'TELEGRAM MINI APP': 'МИНИ-ПРИЛОЖЕНИЕ TELEGRAM',
  'AI Workspace': 'ИИ-помощник',
  'AI WORKSPACE': 'ИИ-ПОМОЩНИК',
  'OWNER': 'ВЛАДЕЛЕЦ',
  'Memory': 'Материалы',
  'AI': 'ИИ',
  'AI INBOX · TELEGRAM': 'ВАЖНОЕ · TELEGRAM',
  'TODAY IN CLARIFY': 'СЕГОДНЯ В CLARIFY',
  'CONTINUE': 'ПРОДОЛЖИТЬ',
  'CLARIFY MEMORY': 'ПАМЯТЬ CLARIFY',
  'SMART SEARCH': 'УМНЫЙ ПОИСК',
  'WRITE WITH CLARIFY': 'НАПИСАТЬ С CLARIFY',
  'AUTONOMOUS COPILOT': 'УМНЫЙ ПОМОЩНИК',
  'AI Inbox': 'Важное',
  'LIVE': 'АКТИВНО',
  'FULL ANALYSIS': 'ПОЛНЫЙ РАЗБОР',
  'OWNER ANALYTICS': 'АНАЛИТИКА ВЛАДЕЛЬЦА',
  'CLARIFY PLANS': 'ТАРИФЫ CLARIFY',
  'INVITE & EARN': 'ПРИГЛАСИ И ПОЛУЧИ БОНУС',
  'BETA · ACTIVE DEVELOPMENT': 'БЕТА · АКТИВНАЯ РАЗРАБОТКА',
  'SMART AI': 'УМНЫЙ ИИ',
  'FAST AI': 'БЫСТРЫЙ ИИ',
  'Smart AI': 'Умный ИИ',
  'Fast AI': 'Быстрый ИИ',
  'Unlimited': 'Без ограничений',
  'OWNER · ПОЛНЫЙ ДОСТУП': 'ВЛАДЕЛЕЦ · ПОЛНЫЙ ДОСТУП',
  'AI за 24ч': 'ИИ за 24 ч',
  'AI запросов': 'ИИ-запросов',
  'ЧТО ТАКОЕ AI-ЗАПРОС?': 'ЧТО ТАКОЕ ИИ-ЗАПРОС?',
}

const REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bAI-запрос/g, 'ИИ-запрос'],
  [/\bAI запрос/g, 'ИИ-запрос'],
  [/\bAI-разбор/g, 'ИИ-разбор'],
  [/\bAI-действ/g, 'ИИ-действ'],
  [/\bSmart AI\b/g, 'Умный ИИ'],
  [/\bFast AI\b/g, 'Быстрый ИИ'],
  [/\bMemory\b/g, 'Материалы'],
  [/\bUnlimited\b/g, 'Без ограничений'],
  [/\bOWNER\b/g, 'ВЛАДЕЛЕЦ'],
  [/\bMini App\b/g, 'мини-приложение'],
]

const ATTRIBUTES = ['aria-label', 'title', 'placeholder', 'alt'] as const

function translate(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return value
  const exact = EXACT[trimmed]
  if (exact) {
    const start = value.indexOf(trimmed)
    return `${value.slice(0, start)}${exact}${value.slice(start + trimmed.length)}`
  }

  let next = value
  for (const [pattern, replacement] of REPLACEMENTS) next = next.replace(pattern, replacement)
  return next
}

function localizeNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const current = root.nodeValue || ''
    const next = translate(current)
    if (next !== current) root.nodeValue = next
    return
  }

  if (!(root instanceof Element)) return

  for (const attribute of ATTRIBUTES) {
    const current = root.getAttribute(attribute)
    if (!current) continue
    const next = translate(current)
    if (next !== current) root.setAttribute(attribute, next)
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    const current = node.nodeValue || ''
    const next = translate(current)
    if (next !== current) node.nodeValue = next
    node = walker.nextNode()
  }

  root.querySelectorAll('*').forEach(element => {
    for (const attribute of ATTRIBUTES) {
      const current = element.getAttribute(attribute)
      if (!current) continue
      const next = translate(current)
      if (next !== current) element.setAttribute(attribute, next)
    }
  })
}

export default function RussianUiWidget() {
  useEffect(() => {
    if (!hasTelegramAuth()) return

    localizeNode(document.body)
    const observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') localizeNode(mutation.target)
        mutation.addedNodes.forEach(localizeNode)
      }
    })
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [])

  return null
}
