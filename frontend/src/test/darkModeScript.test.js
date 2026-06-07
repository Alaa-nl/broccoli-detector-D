// Verifies the pre-paint theme script shipped in index.html. We pull the
// actual <script> out of the file and run it in jsdom, so this tests exactly
// what the browser runs before React mounts (the real FOUC fix).

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function loadInlineThemeScript() {
  const html = readFileSync(resolve('index.html'), 'utf-8');
  // The only attribute-less <script> is the theme script; the app bundle is
  // <script type="module" src=...>, which this pattern deliberately skips.
  const match = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!match) throw new Error('inline theme <script> not found in index.html');
  return match[1];
}

describe('index.html pre-paint dark-mode script', () => {
  it('adds the dark class to <html> when darkMode is saved true', () => {
    localStorage.setItem('darkMode', 'true');

    // eslint-disable-next-line no-new-func
    new Function(loadInlineThemeScript())();

    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('leaves the dark class off when no theme is saved', () => {
    // eslint-disable-next-line no-new-func
    new Function(loadInlineThemeScript())();

    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
