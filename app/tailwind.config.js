/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: 'var(--canvas)',
        bitumen: 'var(--canvas)',
        panel: 'var(--surface)',
        raised: 'var(--surface-raised)',
        bone: '#F1F2F3',
        ash: '#999BA1',
        accent: 'var(--accent)',
        'accent-text': 'var(--accent-text)',
        mblue: '#1C69D4',
        mlight: '#6DB6E8',
        mdark: '#0653B6',
        mred: '#E7222E',
        ok: 'var(--accent-text)',
        warn: '#C6C7CB',
        alert: '#E1E2E5',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'Helvetica Neue', 'Arial', 'sans-serif'],
        cond: ['Inter', '-apple-system', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: { control: '14px', panel: '20px' },
      fontSize: {
        display: ['32px', { lineHeight: '1.12', letterSpacing: '-0.035em', fontWeight: '500' }],
        title: ['20px', { lineHeight: '1.25', letterSpacing: '-0.025em', fontWeight: '500' }],
        body: ['14px', { lineHeight: '1.5' }],
        caption: ['12px', { lineHeight: '1.5' }],
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.025) inset',
        key: '0 1px 2px rgba(0,0,0,0.25)',
      },
    },
  },
  plugins: [],
}
