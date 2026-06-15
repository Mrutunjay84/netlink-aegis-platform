import { BASE_API_URL } from '$lib/utils/constants';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

interface Control {
	key: string;
	ref: string;
	name: string;
	description: string;
	typical_evidence: string;
}

function rows(data: unknown): Record<string, unknown>[] {
	if (Array.isArray(data)) return data as Record<string, unknown>[];
	const results = (data as { results?: unknown })?.results;
	return Array.isArray(results) ? (results as Record<string, unknown>[]) : [];
}

function s(v: unknown): string {
	return v == null ? '' : String(v);
}

export const POST: RequestHandler = async ({ request, fetch }) => {
	let body: { sourceType?: string; id?: string };
	try {
		body = await request.json();
	} catch {
		return json({ error: 'invalid_body' }, { status: 400 });
	}
	const sourceType = body.sourceType === 'framework' ? 'framework' : 'audit';
	const id = s(body.id).trim();
	if (!id) return json({ error: 'missing_id' }, { status: 400 });

	let controls: Control[] = [];

	try {
		if (sourceType === 'audit') {
			// RequirementAssessments embed the requirement node details.
			const res = await fetch(
				`${BASE_API_URL}/requirement-assessments/?compliance_assessment=${encodeURIComponent(id)}`
			);
			if (!res.ok) return json({ error: 'fetch_failed' }, { status: res.status });
			controls = rows(await res.json())
				.filter((ra) => ra.assessable !== false)
				.map((ra) => {
					const req = (ra.requirement ?? {}) as Record<string, unknown>;
					return {
						key: s(req.urn || req.id || ra.id),
						ref: s(req.ref_id),
						name: s(req.name || ra.name),
						description: s(req.description || ra.description),
						typical_evidence: s(req.typical_evidence)
					};
				})
				.filter((c) => c.name || c.description);
		} else {
			const res = await fetch(
				`${BASE_API_URL}/requirement-nodes/?framework=${encodeURIComponent(id)}`
			);
			if (!res.ok) return json({ error: 'fetch_failed' }, { status: res.status });
			controls = rows(await res.json())
				.filter((n) => n.assessable === true)
				.map((n) => ({
					key: s(n.urn || n.id),
					ref: s(n.ref_id),
					name: s(n.name),
					description: s(n.description),
					typical_evidence: s(n.typical_evidence)
				}))
				.filter((c) => c.name || c.description);
		}
	} catch {
		return json({ error: 'fetch_failed' }, { status: 502 });
	}

	return json({ controls });
};
