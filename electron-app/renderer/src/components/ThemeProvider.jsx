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
            // Light theme - 简明模式 (high contrast, clear readability)
            root.style.setProperty('--bg', '#f8f9fa');
            root.style.setProperty('--bg-glow-1', 'transparent');
            root.style.setProperty('--bg-glow-2', 'transparent');
            root.style.setProperty('--panel', '#ffffff');
            root.style.setProperty('--panel-2', '#f5f5f5');
            root.style.setProperty('--text', '#1a1a1a');  // Darker text for better contrast
            root.style.setProperty('--muted', '#4a4a4a'); // Darker muted for readability
            root.style.setProperty('--border', '#d0d0d0');
            root.style.setProperty('--accent', '#2563eb');  // Blue accent for clarity
            root.style.setProperty('--accent-2', '#1d4ed8'); // Deeper blue
            root.style.setProperty('--accent-hover', '#1e40af');
            root.style.setProperty('--input-bg', '#ffffff');
            root.style.setProperty('--code-bg', '#f1f3f4');
            root.style.setProperty('--sidebar-bg', '#ffffff');
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
