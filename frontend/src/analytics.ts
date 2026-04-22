declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void
    dataLayer?: unknown[]
  }
}

const GA_ID = import.meta.env.VITE_GA_MEASUREMENT_ID

export function initAnalytics(): void {
  if (!GA_ID) return

  const script = document.createElement('script')
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`
  script.async = true
  document.head.appendChild(script)

  window.dataLayer = window.dataLayer ?? []
  window.gtag = function (...args: unknown[]) {
    window.dataLayer!.push(args)
  }
  window.gtag('js', new Date())
  window.gtag('config', GA_ID, { send_page_view: false })
}

export function pageview(path: string): void {
  if (!GA_ID || !window.gtag) return
  window.gtag('event', 'page_view', { page_path: path })
}
