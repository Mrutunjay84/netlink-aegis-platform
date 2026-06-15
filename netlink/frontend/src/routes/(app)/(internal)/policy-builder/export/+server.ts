import { BASE_API_URL } from '$lib/utils/constants';
import type { RequestHandler } from './$types';

// Proxies the edited policy HTML to the backend export endpoint and streams the
// generated DOCX/PDF back to the browser. Runs server-side so the request
// carries the authenticated session cookies (the browser cannot call the
// backend API directly).
export const POST: RequestHandler = async ({ request, fetch }) => {
	let body: { format?: string; html?: string; title?: string };
	try {
		body = await request.json();
	} catch {
		return new Response('Invalid request body', { status: 400 });
	}

	const format = (body?.format ?? '').toString();
	const html = (body?.html ?? '').toString();
	const title = (body?.title ?? 'policy').toString();

	if (format !== 'pdf' && format !== 'docx') {
		return new Response('format must be pdf or docx', { status: 400 });
	}
	if (!html.trim()) {
		return new Response('html content is required', { status: 400 });
	}

	let res: Response;
	try {
		res = await fetch(`${BASE_API_URL}/netlink-policy-builder/export/`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ format, html, title })
		});
	} catch (e) {
		console.error('policy-builder: export request to backend failed', e);
		return new Response('The export service is temporarily unavailable. Please try again.', {
			status: 503
		});
	}

	if (!res.ok) {
		const detail = await res.text().catch(() => '');
		console.error('policy-builder: backend export returned', res.status, detail);
		return new Response('Export failed', { status: res.status });
	}

	const buffer = await res.arrayBuffer();
	const headers = new Headers();
	headers.set('Content-Type', res.headers.get('Content-Type') ?? 'application/octet-stream');
	const disposition = res.headers.get('Content-Disposition');
	if (disposition) {
		headers.set('Content-Disposition', disposition);
	}
	headers.set('Cache-Control', 'no-store');
	return new Response(buffer, { status: 200, headers });
};
