import { useEffect } from 'react'

const PAGE_TO_DOCK_LABEL: Record<string, string> = {
  home: 'Главная',
  profile: 'Профиль',
}

export default function DeepLinkWidget() {
  useEffect(() => {
    const page = new URLSearchParams(window.location.search).get('page') || ''
    const label = PAGE_TO_DOCK_LABEL[page]
    if (!label) return

    let done = false
    const open = () => {
      if (done) return true
      const buttons = Array.from(document.querySelectorAll('.v1-dock > button')) as HTMLButtonElement[]
      const target = buttons.find(button => button.querySelector('small')?.textContent?.trim() === label)
      if (!target) return false
      done = true
      target.click()
      return true
    }

    if (open()) return
    const observer = new MutationObserver(() => {
      if (open()) observer.disconnect()
    })
    observer.observe(document.body, { childList: true, subtree: true })
    const timeout = window.setTimeout(() => observer.disconnect(), 6000)
    return () => {
      done = true
      window.clearTimeout(timeout)
      observer.disconnect()
    }
  }, [])

  return null
}
