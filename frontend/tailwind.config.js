/** @type {import('tailwindcss').Config} */
const config = {
  theme: {
    extend: {
      colors: {
        primary: 'var(--primary)',
        'bg-bubble-user': 'var(--bg-bubble-user)',
        'bg-bubble-assistant': 'var(--bg-bubble-assistant)',
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
      },
    },
  },
  plugins: [],
};

export default config;