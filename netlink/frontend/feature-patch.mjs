#!/usr/bin/env node
/**
 * Netlink Aegis - build-time feature patch.
 *
 * Runs against a *copy* of the community frontend tree (the .build dir in dev,
 * or /app in the Docker build), so it never touches committed community source
 * and stays upstream-merge safe (same contract as brand-patch.mjs /
 * deploy-patch.mjs).
 *
 * It wires Netlink overlay features that need a small edit to a community file:
 *   1. Adds the "Policy Builder" item to the governance section of the sidebar
 *      (src/lib/components/SideBar/navData.ts).
 *   2. Adds the i18n message keys the new feature needs to messages/en.json
 *      (en is the inlang baseLocale; other locales fall back to it).
 *
 * The route itself (src/routes/(app)/(internal)/policy-builder/*) ships as an
 * additive overlay file and needs no patching.
 *
 * Idempotent: re-running is a no-op once the edits are present.
 *
 * Run from the frontend root, e.g. `node feature-patch.mjs` with cwd = frontend.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = resolve(process.argv[2] ?? process.cwd());

// 1. Sidebar nav entry --------------------------------------------------------
const NAV_FILE = join(ROOT, 'src', 'lib', 'components', 'SideBar', 'navData.ts');

// Inserted right after the existing `policies` item in the governance section.
const NAV_ITEM = `				{
					name: 'policyBuilder',
					fa_icon: 'fa-solid fa-wand-magic-sparkles',
					href: '/policy-builder',
					permissions: ['add_appliedcontrol']
				},`;

function patchNav() {
	if (!existsSync(NAV_FILE)) {
		console.warn(`[feature-patch] nav file not found: ${NAV_FILE}; skipping`);
		return;
	}
	const original = readFileSync(NAV_FILE, 'utf8');
	if (original.includes("'/policy-builder'")) {
		console.log('[feature-patch] nav entry already present; skipping');
		return;
	}
	// Match the whole `policies` nav object up to and including its `},`.
	const policiesItem = original.match(/\{\s*name:\s*'policies'[\s\S]*?\},/);
	if (!policiesItem) {
		console.warn('[feature-patch] could not locate the policies nav item; skipping');
		return;
	}
	const replacement = `${policiesItem[0]}\n${NAV_ITEM}`;
	const patched = original.replace(policiesItem[0], replacement);
	writeFileSync(NAV_FILE, patched);
	console.log('[feature-patch] added Policy Builder nav entry');
}

// 2. i18n keys ----------------------------------------------------------------
const EN_FILE = join(ROOT, 'messages', 'en.json');

const MESSAGES = {
	policyBuilder: 'Policy Builder',
	policyBuilderDescription:
		'Draft a governance policy with AI assistance, then review, edit, and save it.'
};

function patchMessages() {
	if (!existsSync(EN_FILE)) {
		console.warn(`[feature-patch] en.json not found: ${EN_FILE}; skipping i18n`);
		return;
	}
	const original = readFileSync(EN_FILE, 'utf8');
	let data;
	try {
		data = JSON.parse(original);
	} catch (e) {
		console.warn(`[feature-patch] could not parse en.json: ${e.message}`);
		return;
	}
	let added = 0;
	for (const [key, value] of Object.entries(MESSAGES)) {
		if (!Object.prototype.hasOwnProperty.call(data, key)) {
			data[key] = value;
			added++;
		}
	}
	if (added > 0) {
		writeFileSync(EN_FILE, JSON.stringify(data, null, '\t') + '\n');
	}
	console.log(`[feature-patch] added ${added} i18n key(s) to en.json`);
}

console.log(`[feature-patch] root: ${ROOT}`);
patchNav();
patchMessages();
console.log('[feature-patch] done');
