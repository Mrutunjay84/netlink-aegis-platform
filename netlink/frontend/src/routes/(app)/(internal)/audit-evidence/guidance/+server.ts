import { BASE_API_URL } from '$lib/utils/constants';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, fetch }) => {
	let body: Record<string, unknown>;
	try {
		body = await request.json();
	} catch {
		return json({ error: 'invalid_body' }, { status: 400 });
	}

	const payload = {
		control_ref: String(body.control_ref ?? ''),
		control_name: String(body.control_name ?? ''),
		control_description: String(body.control_description ?? ''),
		typical_evidence: String(body.typical_evidence ?? ''),
		framework: String(body.framework ?? ''),
		scope: String(body.scope ?? ''),
		provider: String(body.provider ?? ''),
		model: String(body.model ?? '')
	};

	const res = await fetch(`${BASE_API_URL}/netlink-audit-evidence/guidance/`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});

	let data: unknown = null;
	try {
		data = await res.json();
	} catch {
		/* non-JSON error body */
	}

	if (!res.ok) {
		const detail =
			(data as { detail?: string })?.detail ?? 'AI guidance failed. Please try again.';
		return json({ error: detail }, { status: res.status });
	}

	return json(data ?? {});
};
