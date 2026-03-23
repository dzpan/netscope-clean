/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        // NetScope Gray Foundation — uses CSS variable RGB channels for opacity modifier support
        gray: {
          950: 'rgb(var(--gray-950-rgb) / <alpha-value>)',
          900: 'rgb(var(--gray-900-rgb) / <alpha-value>)',
          850: 'rgb(var(--gray-850-rgb) / <alpha-value>)',
          800: 'rgb(var(--gray-800-rgb) / <alpha-value>)',
          750: 'rgb(var(--gray-750-rgb) / <alpha-value>)',
          700: 'rgb(var(--gray-700-rgb) / <alpha-value>)',
          600: 'rgb(var(--gray-600-rgb) / <alpha-value>)',
          500: 'rgb(var(--gray-500-rgb) / <alpha-value>)',
          400: 'rgb(var(--gray-400-rgb) / <alpha-value>)',
          300: 'rgb(var(--gray-300-rgb) / <alpha-value>)',
          200: 'rgb(var(--gray-200-rgb) / <alpha-value>)',
          100: 'rgb(var(--gray-100-rgb) / <alpha-value>)',
          50: 'rgb(var(--gray-50-rgb) / <alpha-value>)',
        },
        // NetScope Orange Accent — uses CSS variable RGB channels
        orange: {
          950: 'rgb(var(--orange-950-rgb) / <alpha-value>)',
          900: 'rgb(var(--orange-900-rgb) / <alpha-value>)',
          800: 'rgb(var(--orange-800-rgb) / <alpha-value>)',
          700: 'rgb(var(--orange-700-rgb) / <alpha-value>)',
          600: 'rgb(var(--orange-600-rgb) / <alpha-value>)',
          500: 'rgb(var(--orange-500-rgb) / <alpha-value>)',
          400: 'rgb(var(--orange-400-rgb) / <alpha-value>)',
          300: 'rgb(var(--orange-300-rgb) / <alpha-value>)',
          100: 'rgb(var(--orange-100-rgb) / <alpha-value>)',
          glow: 'var(--orange-glow)',
        },
        // Semantic / Status colors
        status: {
          up: 'var(--status-up)',
          down: 'var(--status-down)',
          warning: 'var(--status-warning)',
          info: 'var(--status-info)',
          unknown: 'var(--status-unknown)',
        },
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        sans: ['Inter', 'sans-serif'],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.8125rem', { lineHeight: '1.25rem' }],
        base: ['0.875rem', { lineHeight: '1.5rem' }],
        lg: ['1rem', { lineHeight: '1.5rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
      },
      borderRadius: {
        sm: '4px',
        DEFAULT: '4px',
        md: '6px',
        lg: '8px',
        none: '0',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        glow: 'var(--shadow-glow)',
        'glow-sm': '0 0 6px rgba(249, 115, 22, 0.2)',
      },
      spacing: {
        sidebar: '280px',
        'sidebar-collapsed': '56px',
        topbar: '48px',
        statusbar: '28px',
      },
      transitionDuration: {
        75: '75ms',
        100: '100ms',
        150: '150ms',
        200: '200ms',
      },
    },
  },
  plugins: [],
}
