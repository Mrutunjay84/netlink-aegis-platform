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

	// Provider picker catalog (non-secret).
	let config: { providers: unknown[]; default: string } = { providers: [], default: '' };
	try {
		const res = await fetch(`${BASE_API_URL}/netlink-policy-builder/config/`);
		if (res.ok) {
			config = await res.json();
		}
	} catch (e) {
		console.error('policy-builder: failed to load provider config', e);
	}

	// Admin settings: a 200 means the current user may manage AI providers.
	let aiSettings: unknown = null;
	let isAiAdmin = false;
	try {
		const res = await fetch(`${BASE_API_URL}/netlink-policy-builder/settings/`);
		if (res.ok) {
			aiSettings = await res.json();
			isAiAdmin = true;
		}
	} catch (e) {
		console.error('policy-builder: failed to load AI settings', e);
	}

	return {
		folders,
		config,
		aiSettings,
		isAiAdmin,
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
			industry: (form.get('industry') ?? '').toString(),
			framework: (form.get('framework') ?? '').toString(),
			additional_context: (form.get('additional_context') ?? '').toString(),
			provider: (form.get('provider') ?? '').toString(),
			model: (form.get('model') ?? '').toString()
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
	},

	// Admin: update provider API keys / base URLs / default provider. An empty
	// api_key field is omitted so the stored key is preserved.
	saveSettings: async ({ request, fetch }) => {
		const form = await request.formData();
		// Provider-agnostic: any field named "<provider>_api_key" / "<provider>_base_url"
		// is collected, so new providers work without code changes here. The
		// backend ignores unknown providers (only managed fields are persisted).
		const providers: Record<string, { api_key?: string; base_url?: string }> = {};
		const ensure = (pid: string) => (providers[pid] ??= {});
		for (const [field, raw] of form.entries()) {
			const value = raw.toString();
			if (field.endsWith('_api_key')) {
				const pid = field.slice(0, -'_api_key'.length);
				if (pid && value.length > 0) ensure(pid).api_key = value;
			} else if (field.endsWith('_base_url')) {
				const pid = field.slice(0, -'_base_url'.length);
				if (pid) ensure(pid).base_url = value;
			}
		}
		// Drop providers that ended up with no fields set.
		for (const pid of Object.keys(providers)) {
			if (Object.keys(providers[pid]).length === 0) delete providers[pid];
		}
		const payload = {
			providers,
			default_provider: (form.get('default_provider') ?? '').toString()
		};
		try {
			const res = await fetch(`${BASE_API_URL}/netlink-policy-builder/settings/`, {
				method: 'PUT',
				body: JSON.stringify(payload)
			});
			if (!res.ok) {
				let detail = 'Could not save settings.';
				try {
					const err = await res.json();
					if (err?.detail) detail = err.detail;
				} catch {
					/* keep default */
				}
				return fail(res.status, { settingsError: detail });
			}
			const settings = await res.json();
			return { settings };
		} catch (e) {
			console.error('policy-builder: settings request failed', e);
			return fail(502, { settingsError: 'Could not reach the server.' });
		}
	}
};
