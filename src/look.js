// The look of the app, from Settings: theme, accent colour, text size, motion, and whether calories show.
// Settings live in `prefs`, which is saved in your account, so they follow you to every device.
import { setVoiceRate } from './lib.js';

export const THEMES = [['system', '📱 Match my phone'], ['light', '☀️ Light'], ['dark', '🌙 Dark']];
export const ACCENTS = [['saffron', 'Saffron', '#b4532a'], ['leaf', 'Curry leaf', '#2f7d4f'], ['peacock', 'Peacock', '#1d6f8c'],
  ['brinjal', 'Brinjal', '#7b3a78'], ['turmeric', 'Turmeric', '#a8740a'], ['chilli', 'Chilli', '#b8322a']];
export const TEXT_SIZES = [[1, 'Normal'], [1.12, 'Large'], [1.25, 'Extra large']];
export const VOICE_SPEEDS = [[0.8, 'Slow'], [0.95, 'Normal'], [1.1, 'Fast']];
export const START_PAGES = [['dashboard', '📊 Dashboard'], ['home', '🍳 Cook'], ['plan', '🗓️ Plan'], ['pantry', '🧺 Kitchen']];
export const CHEF_LENGTHS = [['short', 'Short'], ['normal', 'Normal'], ['detailed', 'Detailed']];
export const CHEF_LANGUAGES = [['auto', 'Same as I write'], ['en', 'English'], ['hi', 'हिन्दी'], ['te', 'తెలుగు'], ['ta', 'தமிழ்']];

export function applyLook(prefs = {}) {
  const root = document.documentElement;
  root.dataset.theme = prefs.theme || 'system';
  root.dataset.accent = prefs.accent || 'saffron';
  root.dataset.calories = prefs.showCalories === false ? 'off' : 'on';
  root.dataset.motion = prefs.reduceMotion ? 'reduce' : '';
  root.style.setProperty('--text-scale', String(prefs.textSize || 1));
  setVoiceRate(prefs.voiceRate || 0.95);
  // The phone's status bar colour follows the theme too.
  const dark = root.dataset.theme === 'dark' || (root.dataset.theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) { meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.appendChild(meta); }
  meta.content = dark ? '#16120f' : (ACCENTS.find(a => a[0] === root.dataset.accent) || ACCENTS[0])[2];
}
