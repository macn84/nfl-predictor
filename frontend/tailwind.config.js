/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        rtc: {
          bg:           '#080b14',
          bg2:          '#0d1117',
          bg3:          '#111827',
          surface:      '#161d2b',
          surface2:     '#1e2736',
          border:       '#1f2d40',
          green:        '#00c851',
          'green-dark': '#007e33',
          gold:         '#ffd700',
          red:          '#e63946',
          text:         '#f0f4f8',
          muted:        '#6b7fa3',
          dim:          '#3d4f6b',
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
