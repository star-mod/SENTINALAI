/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          dark: '#070B14',
          panel: '#0E1626',
          card: '#131C31',
          hover: '#1B2640',
        },
        cyan: {
          glow: '#22D3EE',
          accent: '#06B6D4',
        },
        severity: {
          high: '#EF4444',
          medium: '#F59E0B',
          low: '#22C55E',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        'glow-cyan': '0 0 20px -3px rgba(34, 211, 238, 0.3)',
        'glow-red': '0 0 25px -2px rgba(239, 68, 68, 0.4)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      }
    },
  },
  plugins: [],
}
