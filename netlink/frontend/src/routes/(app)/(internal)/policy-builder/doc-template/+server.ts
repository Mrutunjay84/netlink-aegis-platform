import { BASE_API_URL } from '$lib/utils/constants';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

// Proxy for the company document template settings. PUT is admin-only on the
// backend; sending the (optional) base64 .docx as JSON keeps it simple.
export const PUT: RequestHandler = async ({ request, fetch }) => {
	let body: unknown;
	try {
		body = await request.json();
	} catch {
		return json({ detail: 'Invalid request body.' }, { status: 400 });
	}

	const res = await fetch(`${BASE_API_URL}/netlink-policy-builder/doc-template/`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});

	let data: unknown = null;
	try {
		data = await res.json();
	} catch {
		/* non-JSON error */
	}
	return json(data ?? {}, { status: res.status });
};
