export {}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string
        colorScheme?: 'light' | 'dark'
        themeParams?: Record<string, string>
        viewportHeight?: number
        ready: () => void
        expand: () => void
        close: () => void
        setHeaderColor?: (color: string) => void
        setBackgroundColor?: (color: string) => void
        openInvoice?: (url: string, callback?: (status: string) => void) => void
        openLink?: (url: string) => void
        openTelegramLink?: (url: string) => void
        HapticFeedback?: {
          impactOccurred?: (style: 'light' | 'medium' | 'heavy') => void
          notificationOccurred?: (type: 'error' | 'success' | 'warning') => void
        }
        BackButton?: {
          show: () => void
          hide: () => void
          onClick: (cb: () => void) => void
          offClick: (cb: () => void) => void
        }
      }
    }
  }
}
