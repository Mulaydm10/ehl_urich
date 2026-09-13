/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: '#0f1012',
        panel: '#16171a',
        raised: '#23252a',
        line: '#2e3137',
        bone: '#F1F2F3',
        ash: '#9a9ca3',
        dim: '#6b6e76',
        accent: '#1C69D4',
        mlight: '#6DB6E8',
        mred: '#E7222E',
        mint: '#3ED598',
        amber: '#F5A524',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        glass: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 12px 40px -12px rgba(0,0,0,0.7)',
        glow: '0 0 0 1px rgba(28,105,212,0.5), 0 0 24px -4px rgba(28,105,212,0.6)',
        card: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 6px 18px -8px rgba(0,0,0,0.6)',
      },
      keyframes: {
        rise: { from: { opacity: 0, transform: 'translateY(6px)' }, to: { opacity: 1, transform: 'none' } },
        pulse2: { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.35 } },
        shimmer: { from: { backgroundPosition: '-200% 0' }, to: { backgroundPosition: '200% 0' } },
      },
      animation: {
        rise: 'rise 320ms cubic-bezier(0.2, 0.7, 0.2, 1) both',
        pulse2: 'pulse2 1.6s ease-in-out infinite',
        shimmer: 'shimmer 1.4s linear infinite',
      },
    },
  },
  plugins: [],
}
