import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#bbb5ae',
          raised: '#c8c2bb',
          high: '#a8a29b',
        },
        accent: {
          DEFAULT: '#d94e00',
          dark: '#a03800',
          orange: '#ff9a4a',
          orangeDark: '#703a1e',
        },
        foreground: '#1e1a18',
        muted: '#7a7470',
        border: '#9a9490',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'Helvetica Neue', 'sans-serif'],
        mono: ['SF Mono', 'Monaco', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
