import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Copy, Gift, Send, Users } from 'lucide-react'
import { api, haptic, hasTelegramAuth, successHaptic } from './api'

type GrowthStats = {
  invited: number
  activated: number
  earned_requests: number
  bonus_requests: number
  referral_bonus: number
  referral_link: string
  source: string
  campaign?: string | null
}

function openTelegramShare(link: string) {
  const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent('Попробуй Clarify — он разбирает голосовые, документы, скриншоты и переписки вместо тебя.')}`
  const webApp = window.Telegram?.WebApp as unknown as { openTelegramLink?: (url: string) => void } | undefined
  if (webApp?.openTelegramLink) webApp.openTelegramLink(share)
  else window.location.assign(share)
}

export default function ReferralProfileWidget() {
  const [slot, setSlot] = useState<HTMLElement | null>(null)
  const [stats, setStats] = useState<GrowthStats | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!hasTelegramAuth()) return
    let ownedSlot: HTMLElement | null = null

    const findProfile = () => {
      const profileCard = document.querySelector('.v1-profile-card') as HTMLElement | null
      if (!profileCard?.parentElement) {
        setSlot(null)
        return
      }
      const parent = profileCard.parentElement
      let target = parent.querySelector('#clarify-referral-slot') as HTMLElement | null
      if (!target) {
        target = document.createElement('div')
        target.id = 'clarify-referral-slot'
        const statsGrid = parent.querySelector('.v1-stats')
        if (statsGrid) statsGrid.insertAdjacentElement('afterend', target)
        else profileCard.insertAdjacentElement('afterend', target)
        ownedSlot = target
      }
      setSlot(target)
    }

    findProfile()
    const observer = new MutationObserver(findProfile)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      observer.disconnect()
      if (ownedSlot?.isConnected) ownedSlot.remove()
      setSlot(null)
    }
  }, [])

  useEffect(() => {
    if (!slot) return
    let cancelled = false
    void api<GrowthStats>('/api/profile/stats')
      .then(value => { if (!cancelled) setStats(value) })
      .catch(() => { if (!cancelled) setStats(null) })
    return () => { cancelled = true }
  }, [slot])

  if (!slot || !stats) return null

  const copy = async () => {
    haptic()
    try {
      await navigator.clipboard.writeText(stats.referral_link)
      setCopied(true)
      successHaptic()
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      window.prompt('Скопируй реферальную ссылку', stats.referral_link)
    }
  }

  return createPortal(
    <section className="referral-card">
      <div className="referral-head">
        <span className="referral-icon"><Gift /></span>
        <div>
          <span className="v1-eyebrow">INVITE & EARN</span>
          <h3>Пригласи друга</h3>
          <p>После его первого успешного AI-разбора вы оба получите <b>+{stats.referral_bonus}</b> запросов.</p>
        </div>
      </div>

      <div className="referral-stats">
        <span><Users /><small>Приглашено</small><b>{stats.invited}</b></span>
        <span><Gift /><small>Активировано</small><b>{stats.activated}</b></span>
        <span><span className="referral-plus">+</span><small>Заработано</small><b>{stats.earned_requests}</b></span>
      </div>

      <div className="referral-actions">
        <button className="referral-primary" onClick={() => { haptic('medium'); openTelegramShare(stats.referral_link) }}>
          <Send /> Пригласить друга
        </button>
        <button className="referral-copy" onClick={() => void copy()}>
          <Copy /> {copied ? 'Скопировано' : 'Скопировать'}
        </button>
      </div>

      <small className="referral-note">Бонус начисляется только после первого реального AI-разбора приглашённого пользователя.</small>
    </section>,
    slot,
  )
}
