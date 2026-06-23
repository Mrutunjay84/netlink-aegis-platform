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
// Scan the whole src tree (not just routes): the csrftoken/LOCALE cookies are
// set in src/hooks.server.ts, which lives outside src/routes. Missing it means
// the csrftoken cookie stays Secure and is dropped over plain HTTP, so login
// silently fails.
const ROUTES_DIR = join(ROOT, 'src');

const FROM = /secure:\s*true/g;
const TO = "secure: process.env.SECURE_COOKIES !== 'false'";

// `cookies.delete(...)` calls don't pass an explicit `secure` flag, so SvelteKit
// defaults it to `true` for any non-localhost host. Over plain HTTP the browser
// then ignores the deletion Set-Cookie (Secure cookies require HTTPS), so the
// auth cookies are never cleared and LOGOUT silently fails. Inject the same
// env-driven secure flag into every `cookies.delete(name, { ... })` call.
const DELETE_FROM = /(cookies\.delete\(\s*['"][^'"]+['"]\s*,\s*\{)([\s\S]*?)(\}\s*\))/g;

function collectServerFiles(dir, acc) {
	if (!existsSync(dir)) return acc;
	for (const entry of readdirSync(dir)) {
		const full = join(dir, entry);
		const st = statSync(full);
		if (st.isDirectory()) {
			collectServerFiles(full, acc);
		} else if (
			// `*.server.ts` (hooks, +page.server.ts, +layout.server.ts) AND
			// `+server.ts` route endpoints. The latter set auth cookies and handle
			// LOGOUT (logout/+server.ts) but do NOT end in `.server.ts` (the `+`
			// replaces the dot), so they were previously missed — leaving logout's
			// cookie deletes Secure-by-default and broken over plain HTTP.
			/(?:\.server|\+server)\.(?:ts|js)$/.test(entry)
		) {
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
		let patched = original;

		// 1) `secure: true` on cookies.set(...) -> env-driven.
		FROM.lastIndex = 0;
		patched = patched.replace(FROM, TO);

		// 2) cookies.delete(name, { ... }) -> ensure an env-driven secure flag,
		//    so logout actually clears cookies over plain HTTP.
		DELETE_FROM.lastIndex = 0;
		patched = patched.replace(DELETE_FROM, (full, head, body, tail) => {
			if (/secure\s*:/.test(body)) return full; // already explicit
			const trimmed = body.replace(/\s+$/, '');
			const sep = trimmed.trimEnd().endsWith(',') || trimmed.trim() === '' ? '' : ',';
			return `${head}${trimmed}${sep} ${TO} ${tail}`;
		});

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
