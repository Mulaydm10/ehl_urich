/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: '#191a1c',
        panel: '#202123',
        raised: '#2b2d30',
        bone: '#F1F2F3',
        ash: '#999BA1',
        accent: '#1C69D4',
        mlight: '#6DB6E8',
        mred: '#E7222E',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
