import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { parseDocument } from 'yaml';

const site = parseDocument(readFileSync(new URL('../mkdocs.yml', import.meta.url), 'utf8'));
const siteUrl = site.get('site_url');
if (typeof siteUrl !== 'string') throw new Error('mkdocs.yml must define site_url');
const proxyPrefix = (process.env.IMMUKNOW_PROXY_PREFIX ?? '').replace(/\/+$/, '');
if (proxyPrefix && (!/^\/[A-Za-z0-9_./~-]+$/.test(proxyPrefix) || proxyPrefix.startsWith('//') || proxyPrefix.split('/').some(part => part === '.' || part === '..'))) {
  throw new Error('IMMUKNOW_PROXY_PREFIX must be an absolute URL path prefix');
}
const base = proxyPrefix + new URL('playground/', siteUrl).pathname;

export default defineConfig({
  base,
  worker: { format: 'es' },
  build: { rolldownOptions: { input: { app: 'index.html', proof: 'proof.html' } } },
});
