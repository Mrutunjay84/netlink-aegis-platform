#!/usr/bin/env node
/**
 * Netlink Aegis - build-time deploy patch (cookie security).
 *
 * The community login/SSO server routes set their auth cookies with
 * `secure: true` hardcoded. Browsers only store `Secure` cookies over HTTPS
 * (or http://localhost), so a plain-HTTP deployment accessed from another
 * machine can never log in (the token cookie is silently dropped).
 *
 * This patch rewrites those hardcoded `secure: true` flags to be controlled at
 * RUNTIME by the SECURE_COOKIES environment variable:
 *
 *     secure: process.env.SECURE_COOKIES !== 'false'
 *
 * Default behaviour is unchanged (secure) unless you explicitly set
 * SECURE_COOKIES=false on the frontend service (the plain-HTTP compose does
 * this). HTTPS deployments leave it unset and keep Secure cookies.
 *
 * Like brand-patch.mjs, it runs against a *copy* of the community tree and
 * never edits the committed community source, so it is upstream-merge safe.
 *
 * Run from the frontend root, e.g. `node deploy-patch.mjs` with cwd = frontend.
 */
import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = resolve(process.argv[2] ?? process.cwd());
const ROUTES_DIR = join(ROOT, 'src', 'routes');

const FROM = /secure:\s*true/g;
const TO = "secure: process.env.SECURE_COOKIES !== 'false'";

function collectServerFiles(dir, acc) {
	if (!existsSync(dir)) return acc;
	for (const entry of readdirSync(dir)) {
		const full = join(dir, entry);
		const st = statSync(full);
		if (st.isDirectory()) {
			collectServerFiles(full, acc);
		} else if (entry.endsWith('.server.ts') || entry.endsWith('.server.js')) {
			acc.push(full);
		}
	}
	return acc;
}

function patchCookies() {
	if (!existsSync(ROUTES_DIR)) {
		console.warn(`[deploy-patch] routes dir not found at ${ROUTES_DIR}; skipping`);
		return;
	}
	const files = collectServerFiles(ROUTES_DIR, []);
	let changed = 0;
	for (const path of files) {
		const original = readFileSync(path, 'utf8');
		if (!FROM.test(original)) continue;
		FROM.lastIndex = 0;
		const patched = original.replace(FROM, TO);
		if (patched !== original) {
			writeFileSync(path, patched);
			changed++;
			console.log(`[deploy-patch] cookie-secure made env-driven in ${path.slice(ROOT.length + 1)}`);
		}
	}
	console.log(`[deploy-patch] patched ${changed} server file(s)`);
}

console.log(`[deploy-patch] root: ${ROOT}`);
patchCookies();
console.log('[deploy-patch] done');
