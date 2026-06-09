import { BASE_API_URL } from '$lib/utils/constants';
import { fail } from '@sveltejs/kit';
import { m } from '$paraglide/messages';
import type { Actions, PageServerLoad } from './$types';

interface FolderOption {
	id: string;
	name: string;
}

export const load: PageServerLoad = async ({ fetch }) => {
	let folders: FolderOption[] = [];
	try {
		const res = await fetch(`${BASE_API_URL}/folders/`);
		if (res.ok) {
			const data = await res.json();
			const rows = Array.isArray(data) ? data : (data.results ?? []);
			folders = rows
				.map((f: Record<string, unknown>) => ({
					id: String(f.id ?? ''),
					name: String(f.str ?? f.name ?? f.id ?? '')
				}))
				.filter((f: FolderOption) => f.id);
		}
	} catch (e) {
		console.error('policy-builder: failed to load folders', e);
	}

	return {
		folders,
		title: m.policyBuilder()
	};
};

export const actions: Actions = {
	// Proposal only: asks the backend AI to draft a policy. Nothing is saved.
	draft: async ({ request, fetch }) => {
		const form = await request.formData();
		const topic = (form.get('topic') ?? '').toString().trim();
		if (!topic) {
			return fail(400, { draftError: 'Please enter a policy topic.' });
		}
		const payload = {
			topic,
			audience: (form.get('audience') ?? '').toString(),
			framework: (form.get('framework') ?? '').toString(),
			additional_context: (form.get('additional_context') ?? '').toString()
		};
		try {
			const res = await fetch(`${BASE_API_URL}/netlink-policy-builder/draft/`, {
				method: 'POST',
				body: JSON.stringify(payload)
			});
			if (!res.ok) {
				return fail(res.status, {
					draftError: 'The AI service could not generate a draft. Please try again.'
				});
			}
			const draft = await res.json();
			return { draft };
		} catch (e) {
			console.error('policy-builder: draft request failed', e);
			return fail(502, { draftError: 'Could not reach the AI service.' });
		}
	},

	// Persists the (possibly user-edited) draft as a Policy. The backend
	// enforces the per-folder add_appliedcontrol permission.
	save: async ({ request, fetch }) => {
		const form = await request.formData();
		const payload = {
			folder: (form.get('folder') ?? '').toString(),
			name: (form.get('name') ?? '').toString().trim(),
			description: (form.get('description') ?? '').toString(),
			ref_id: (form.get('ref_id') ?? '').toString().trim()
		};
		if (!payload.folder) {
			return fail(400, { saveError: 'Please choose a domain.' });
		}
		if (!payload.name) {
			return fail(400, { saveError: 'Please enter a policy name.' });
		}
		try {
			const res = await fetch(`${BASE_API_URL}/netlink-policy-builder/save/`, {
				method: 'POST',
				body: JSON.stringify(payload)
			});
			if (!res.ok) {
				let detail = 'Could not save the policy.';
				try {
					const err = await res.json();
					if (err?.detail) detail = err.detail;
				} catch {
					/* keep default */
				}
				return fail(res.status, { saveError: detail });
			}
			const saved = await res.json();
			return { saved };
		} catch (e) {
			console.error('policy-builder: save request failed', e);
			return fail(502, { saveError: 'Could not reach the server.' });
		}
	}
};
