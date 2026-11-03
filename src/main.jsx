import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(<App />);

// Offline support + "Add to Home screen" (only on a real website or localhost).
try {
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost') && !navigator.webdriver) {
    window.addEventListener('load', () => { try { navigator.serviceWorker.register('sw.js').catch(() => {}); } catch { /* not allowed here */ } });
  }
} catch { /* some embedded viewers block service workers */ }
