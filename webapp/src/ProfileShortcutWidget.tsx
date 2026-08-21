import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { UserRound } from 'lucide-react'
import { api, haptic, hasTelegramAuth, Me } from './api'

export default function ProfileShortcutWidget() {
  const [topbar, setTopbar] = useState<HTMLElement | null>(null)
  const [profileButton, setProfileButton] = useState<HTMLButtonElement | null>(null)
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    if (!hasTelegramAuth()) return
    void api<Me>('/api/me').then(setMe).catch(() => undefined)

    const find = () => {
      const bar = document.querySelector('.v1-topbar') as HTMLElement | null
      const buttons = Array.from(document.querySelectorAll('.v1-dock > button')) as HTMLButtonElement[]
      const profile = buttons.find(button => button.querySelector('small')?.textContent?.trim() === 'Профиль') || null
      if (profile) profile.classList.add('v1-dock-profile-hidden')
      setTopbar(bar)
      setProfileButton(profile)
    }

    const openPlansFromBadge = (event: MouseEvent) => {
      const target = event.target as Element | null
      if (!target?.closest('.v1-plan')) return
      event.preventDefault()
      event.stopPropagation()
      haptic()
      window.dispatchEvent(new Event('clarify:open-plans'))
    }

    find()
    const observer = new MutationObserver(find)
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('click', openPlansFromBadge, true)
    return () => {
      observer.disconnect()
      document.removeEventListener('click', openPlansFromBadge, true)
    }
  }, [])

  if (!hasTelegramAuth() || !topbar) return null

  const initial = (me?.first_name || '').trim().charAt(0).toUpperCase()
  return createPortal(
    <button
      className="v1-profile-shortcut"
      aria-label="Открыть профиль"
      title="Профиль"
      onClick={() => {
        haptic()
        profileButton?.click()
      }}
    >
      <span>{initial || <UserRound />}</span>
      <i />
    </button>,
    topbar,
  )
}
