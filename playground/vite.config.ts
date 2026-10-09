import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { parseDocument } from 'yaml';

const site = parseDocument(readFileSync(new URL('../mkdocs.yml', import.meta.url), 'utf8'));
const siteUrl = site.get('site_url');
if (typeof siteUrl !== 'string') throw new Error('mkdocs.yml must define site_url');
const base = new URL('playground/', siteUrl).pathname;

export default defineConfig({
  base,
  worker: { format: 'es' },
  build: { rolldownOptions: { input: 'proof.html' } },
});
