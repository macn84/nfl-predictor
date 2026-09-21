/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        app: {
          bg:           'var(--brand-bg)',
          bg2:          'var(--brand-bg2)',
          bg3:          'var(--brand-bg3)',
          surface:      'var(--brand-surface)',
          surface2:     'var(--brand-surface2)',
          border:       'var(--brand-border)',
          green:        'var(--brand-primary)',
          'green-dark': 'var(--brand-primary-dark)',
          gold:         'var(--brand-accent)',
          red:          'var(--brand-danger)',
          text:         'var(--brand-text)',
          muted:        'var(--brand-muted)',
          dim:          'var(--brand-dim)',
        },
      },
      fontFamily: {
        display: ['"Bebas Neue"', 'Impact', 'sans-serif'],
        mono:    ['"JetBrains Mono"', '"Courier New"', 'monospace'],
      },
    },
  },
  plugins: [],
}
