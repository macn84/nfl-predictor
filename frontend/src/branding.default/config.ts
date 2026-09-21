export type BrandConfig = {
  appName: string
  appTagline: string
  /** Image shown in the nav bar instead of text. Null = render text fallback. */
  navLogo: { src: string; alt: string } | null
  /** Full-width banner image at the top of the weekly dashboard. Null = no banner. */
  dashboardHeader: { src: string; alt: string } | null
  /** URL the nav logo/title links to. Null = default to "/". */
  logoLink: string | null
}

export const brand: BrandConfig = {
  appName: 'NFL Predictor',
  appTagline: 'Game predictions powered by data',
  navLogo: null,
  dashboardHeader: null,
  logoLink: null,
}
