import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#c5bfb8',
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
        muted: '#636060',
        border: '#9a9490',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'Helvetica Neue', 'sans-serif'],
        mono: ['SF Mono', 'Monaco', 'Menlo', 'monospace'],
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        fadeIn: 'fadeIn 0.5s ease-in-out',
      },
    },
  },
  plugins: [],
} satisfies Config
