/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                bg: 'var(--bg)',
                'bg-glow-1': 'var(--bg-glow-1)',
                'bg-glow-2': 'var(--bg-glow-2)',
                panel: 'var(--panel)',
                'panel-2': 'var(--panel-2)',
                text: 'var(--text)',
                muted: 'var(--muted)',
                border: 'var(--border)',
                accent: 'var(--accent)',
                'accent-2': 'var(--accent-2)',
                'accent-hover': 'var(--accent-hover)',
                'accent-2-hover': 'var(--accent-2-hover)',
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            }
        },
    },
    plugins: [],
}
