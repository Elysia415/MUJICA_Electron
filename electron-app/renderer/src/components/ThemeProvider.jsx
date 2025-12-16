import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext({
    theme: 'dark',
    toggleTheme: () => { },
    setTheme: (t) => { }
});

export function useTheme() {
    return useContext(ThemeContext);
}

export function ThemeProvider({ children }) {
    const [theme, setThemeState] = useState('dark');

    useEffect(() => {
        // Load from localStorage
        const saved = localStorage.getItem('mujica-theme');
        if (saved === 'light' || saved === 'dark') {
            setThemeState(saved);
        }
    }, []);

    useEffect(() => {
        // Apply theme to document
        const root = document.documentElement;

        if (theme === 'light') {
            // Light theme CSS variables (from Streamlit)
            root.style.setProperty('--bg', '#ffffff');
            root.style.setProperty('--bg-glow-1', 'transparent');
            root.style.setProperty('--bg-glow-2', 'transparent');
            root.style.setProperty('--panel', '#ffffff');
            root.style.setProperty('--panel-2', '#fcfcfc');
            root.style.setProperty('--text', '#202124');
            root.style.setProperty('--muted', '#5f6368');
            root.style.setProperty('--border', '#dadce0');
            root.style.setProperty('--accent', '#bdbdbd');
            root.style.setProperty('--accent-2', '#757575');
            root.style.setProperty('--accent-hover', '#9e9e9e');
            root.style.setProperty('--input-bg', '#ffffff');
            root.style.setProperty('--code-bg', '#f1f3f4');
            root.style.setProperty('--sidebar-bg', '#f8f9fa');
        } else {
            // Dark theme (Ave Mujica Gothic)
            root.style.setProperty('--bg', '#050505');
            root.style.setProperty('--bg-glow-1', 'rgba(139, 0, 50, 0.35)');
            root.style.setProperty('--bg-glow-2', 'rgba(75, 0, 130, 0.25)');
            root.style.setProperty('--panel', 'rgba(18, 18, 24, 0.70)');
            root.style.setProperty('--panel-2', 'rgba(26, 26, 32, 0.65)');
            root.style.setProperty('--text', '#eaeaea');
            root.style.setProperty('--muted', '#999999');
            root.style.setProperty('--border', 'rgba(197, 160, 89, 0.6)');
            root.style.setProperty('--accent', '#8a002b');
            root.style.setProperty('--accent-2', '#c5a059');
            root.style.setProperty('--accent-hover', '#a30033');
            root.style.setProperty('--input-bg', 'rgba(0, 0, 0, 0.35)');
            root.style.setProperty('--code-bg', 'rgba(0, 0, 0, 0.4)');
            root.style.setProperty('--sidebar-bg', 'rgba(10, 10, 12, 0.85)');
        }

        localStorage.setItem('mujica-theme', theme);
    }, [theme]);

    const toggleTheme = () => {
        setThemeState(prev => prev === 'dark' ? 'light' : 'dark');
    };

    const setTheme = (t) => {
        if (t === 'light' || t === 'dark') setThemeState(t);
    };

    return (
        <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
            {children}
        </ThemeContext.Provider>
    );
}
