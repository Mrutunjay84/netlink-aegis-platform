import { BASE_API_URL } from '$lib/utils/constants';
import { m } from '$paraglide/messages';
import type { PageServerLoad } from './$types';

interface AuditOption {
	id: string;
	name: string;
	framework: string;
	frameworkId: string;
}
interface FrameworkOption {
	id: string;
	name: string;
}

function rows(data: unknown): Record<string, unknown>[] {
	if (Array.isArray(data)) return data as Record<string, unknown>[];
	const results = (data as { results?: unknown })?.results;
	return Array.isArray(results) ? (results as Record<string, unknown>[]) : [];
}

function rel(value: unknown): { id: string; str: string } {
	if (value && typeof value === 'object') {
		const o = value as Record<string, unknown>;
		return { id: String(o.id ?? ''), str: String(o.str ?? o.name ?? '') };
	}
	return { id: '', str: '' };
}

export const load: PageServerLoad = async ({ fetch }) => {
	let audits: AuditOption[] = [];
	let frameworks: FrameworkOption[] = [];
	let config: { providers: unknown[]; default: string } = { providers: [], default: '' };

	try {
		const res = await fetch(`${BASE_API_URL}/compliance-assessments/`);
		if (res.ok) {
			audits = rows(await res.json())
				.map((a) => {
					const fw = rel(a.framework);
					return {
						id: String(a.id ?? ''),
						name: String(a.str ?? a.name ?? a.id ?? ''),
						framework: fw.str,
						frameworkId: fw.id
					};
				})
				.filter((a) => a.id);
		}
	} catch {
		/* leave empty */
	}

	try {
		const res = await fetch(`${BASE_API_URL}/frameworks/`);
		if (res.ok) {
			frameworks = rows(await res.json())
				.map((f) => ({
					id: String(f.id ?? ''),
					name: String(f.name ?? f.str ?? f.id ?? '')
				}))
				.filter((f) => f.id);
		}
	} catch {
		/* leave empty */
	}

	try {
		const res = await fetch(`${BASE_API_URL}/netlink-audit-evidence/config/`);
		if (res.ok) {
			const data = await res.json();
			config = {
				providers: Array.isArray(data?.providers) ? data.providers : [],
				default: String(data?.default ?? '')
			};
		}
	} catch {
		/* leave empty */
	}

	return {
		audits,
		frameworks,
		config,
		title: m.auditEvidence()
	};
};
