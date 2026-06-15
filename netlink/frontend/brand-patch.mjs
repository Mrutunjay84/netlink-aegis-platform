#!/usr/bin/env node
/**
 * Netlink Aegis - build-time white-label patch.
 *
 * Runs against a *copy* of the community frontend tree (the rsync/.build dir in
 * dev, or /app in the Docker build). It never touches the committed community
 * source, so it is safe to re-run after every upstream merge.
 *
 * It performs two things:
 *   1. Rebrands the "CISO Assistant" phrase in every i18n message value across
 *      all locales in messages/*.json.
 *   2. Rebrands the handful of hardcoded "CISO Assistant" literals in specific
 *      Svelte source files (title bar, TOTP issuer, chat widget, logo alt...).
 *
 * Run from the frontend root, e.g. `node brand-patch.mjs` with cwd = frontend.
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = resolve(process.argv[2] ?? process.cwd());
const BRAND_NEW = 'Netlink Aegis';

// Order matters: longer / hyphenated variants first.
const PHRASE_REPLACEMENTS = [
	[/CISO[- ]Assistant/g, BRAND_NEW],
	[/Ciso[- ]assistant/g, BRAND_NEW]
];

function applyPhrases(text) {
	let out = text;
	for (const [pattern, replacement] of PHRASE_REPLACEMENTS) {
		out = out.replace(pattern, replacement);
	}
	return out;
}

function walkValues(node, fn) {
	if (typeof node === 'string') return fn(node);
	if (Array.isArray(node)) return node.map((v) => walkValues(v, fn));
	if (node && typeof node === 'object') {
		const out = {};
		for (const [k, v] of Object.entries(node)) out[k] = walkValues(v, fn);
		return out;
	}
	return node;
}

function patchMessages() {
	const dir = join(ROOT, 'messages');
	if (!existsSync(dir)) {
		console.warn(`[brand-patch] messages dir not found at ${dir}; skipping i18n`);
		return;
	}
	let changed = 0;
	for (const file of readdirSync(dir)) {
		if (!file.endsWith('.json')) continue;
		const path = join(dir, file);
		const original = readFileSync(path, 'utf8');
		let data;
		try {
			data = JSON.parse(original);
		} catch (e) {
			console.warn(`[brand-patch] could not parse ${file}: ${e.message}`);
			continue;
		}
		const patched = walkValues(data, applyPhrases);
		const serialized = JSON.stringify(patched, null, '\t') + '\n';
		if (serialized !== original) {
			writeFileSync(path, serialized);
			changed++;
		}
	}
	console.log(`[brand-patch] rebranded ${changed} message file(s)`);
}

// Files containing hardcoded "CISO Assistant" string literals (not i18n keys).
const SOURCE_FILES = [
	'src/routes/(app)/+layout.svelte',
	'src/routes/(app)/setup-mfa/+page.svelte',
	'src/routes/(app)/(third-party)/my-profile/settings/mfa/components/ActivateTOTPModal.svelte',
	'src/lib/components/ChatWidget/ChatWidget.svelte',
	'src/routes/(app)/(internal)/quantitative-risk-studies/[id=uuid]/executive-summary/+page.svelte',
	'src/lib/components/Logo/Logo.svelte'
];

// Exact literal replacements that are not the "CISO Assistant" phrase. Each
// entry is [relativeFile, [[from, to], ...]]. Idempotent: skips if `from` is
// absent (e.g. already patched on a previous run).
const LITERAL_REPLACEMENTS = [
	[
		'src/routes/+layout.svelte',
		[['<link rel="icon" href="/favicon.ico" />', '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />']]
	],
	['src/lib/components/Logo/Logo.svelte', [['Ciso-assistant icon', 'Netlink Aegis icon']]]
];

function patchSourceFiles() {
	let changed = 0;
	for (const rel of SOURCE_FILES) {
		const path = join(ROOT, rel);
		if (!existsSync(path)) {
			console.warn(`[brand-patch] source file not found: ${rel}`);
			continue;
		}
		const original = readFileSync(path, 'utf8');
		const patched = applyPhrases(original);
		if (patched !== original) {
			writeFileSync(path, patched);
			changed++;
		}
	}
	console.log(`[brand-patch] rebranded ${changed} source file(s)`);
}

function patchLiterals() {
	let changed = 0;
	for (const [rel, pairs] of LITERAL_REPLACEMENTS) {
		const path = join(ROOT, rel);
		if (!existsSync(path)) {
			console.warn(`[brand-patch] literal target not found: ${rel}`);
			continue;
		}
		let text = readFileSync(path, 'utf8');
		const before = text;
		for (const [from, to] of pairs) text = text.split(from).join(to);
		if (text !== before) {
			writeFileSync(path, text);
			changed++;
		}
	}
	console.log(`[brand-patch] applied literal replacements in ${changed} file(s)`);
}

// Inject the Netlink minimalistic theme overlay into app.css so it loads after
// the community ciso-theme (our token overrides then win). Idempotent.
function patchTheme() {
	const path = join(ROOT, 'src/app.css');
	if (!existsSync(path)) {
		console.warn('[brand-patch] src/app.css not found; skipping theme inject');
		return;
	}
	const text = readFileSync(path, 'utf8');
	const importLine = "@import './netlink-theme.css';";
	if (text.includes(importLine)) {
		console.log('[brand-patch] theme already injected');
		return;
	}
	// Place right after the skeleton-svelte import (last of the @import block).
	const anchor = "@import '@skeletonlabs/skeleton-svelte';";
	let patched;
	if (text.includes(anchor)) {
		patched = text.replace(anchor, `${anchor}\n${importLine}`);
	} else {
		// Fallback: prepend (still before non-import rules in our overlay file).
		patched = `${importLine}\n${text}`;
	}
	writeFileSync(path, patched);
	console.log('[brand-patch] injected netlink-theme.css import into app.css');
}

console.log(`[brand-patch] root: ${ROOT}`);
patchMessages();
patchSourceFiles();
patchLiterals();
patchTheme();
console.log('[brand-patch] done');
