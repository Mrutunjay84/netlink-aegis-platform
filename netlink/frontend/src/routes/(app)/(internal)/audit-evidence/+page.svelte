<script lang="ts">
	import { onMount } from 'svelte';
	import { m } from '$paraglide/messages';

	let { data } = $props();

	interface ProviderInfo {
		id: string;
		label: string;
		models: string[];
		default_model: string;
	}
	interface Control {
		key: string;
		ref: string;
		name: string;
		description: string;
		typical_evidence: string;
	}
	interface GuidanceState {
		open: boolean;
		loading: boolean;
		html: string;
		error: string;
	}

	const providers: ProviderInfo[] = data.config?.providers ?? [];
	const hasProvider = providers.length > 0;
	const audits = data.audits ?? [];
	const frameworks = data.frameworks ?? [];

	// AI provider + model (same pattern as the Policy Builder)
	let selectedProvider = $state(data.config?.default ?? (providers[0]?.id ?? ''));
	let modelMode = $state<'preset' | 'custom'>('preset');
	let selectedModel = $state('');
	let customModel = $state('');
	const currentProvider = $derived(providers.find((p) => p.id === selectedProvider));
	const resolvedModel = $derived(modelMode === 'custom' ? customModel.trim() : selectedModel);

	$effect(() => {
		const p = providers.find((x) => x.id === selectedProvider);
		if (p && modelMode === 'preset' && !p.models.includes(selectedModel)) {
			selectedModel = p.default_model || p.models[0] || '';
		}
	});

	// Scope (kept in the browser only)
	const SCOPE_KEY = 'netlink_audit_scope';
	let scope = $state('');
	onMount(() => {
		try {
			scope = localStorage.getItem(SCOPE_KEY) ?? '';
		} catch {
			/* ignore */
		}
	});
	$effect(() => {
		try {
			localStorage.setItem(SCOPE_KEY, scope);
		} catch {
			/* ignore */
		}
	});

	// Source selection
	let sourceType = $state<'audit' | 'framework'>(audits.length ? 'audit' : 'framework');
	let selectedAuditId = $state('');
	let selectedFrameworkId = $state('');

	const frameworkName = $derived.by(() => {
		if (sourceType === 'audit') {
			return audits.find((a) => a.id === selectedAuditId)?.framework ?? '';
		}
		return frameworks.find((f) => f.id === selectedFrameworkId)?.name ?? '';
	});
	const selectedSourceId = $derived(sourceType === 'audit' ? selectedAuditId : selectedFrameworkId);

	// Controls
	let controls = $state<Control[]>([]);
	let loadingControls = $state(false);
	let controlsError = $state('');
	let search = $state('');
	let loadedLabel = $state('');

	const filteredControls = $derived.by(() => {
		const q = search.trim().toLowerCase();
		if (!q) return controls;
		return controls.filter(
			(c) =>
				c.name.toLowerCase().includes(q) ||
				c.ref.toLowerCase().includes(q) ||
				c.description.toLowerCase().includes(q)
		);
	});

	// Per-control guidance state, keyed by control.key
	let guidance = $state<Record<string, GuidanceState>>({});

	async function loadControls() {
		if (!selectedSourceId || loadingControls) return;
		loadingControls = true;
		controlsError = '';
		controls = [];
		guidance = {};
		try {
			const res = await fetch('/audit-evidence/controls', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ sourceType, id: selectedSourceId })
			});
			const body = await res.json();
			if (!res.ok) {
				controlsError = 'Could not load controls for this selection.';
				return;
			}
			controls = (body.controls ?? []) as Control[];
			loadedLabel =
				sourceType === 'audit'
					? (audits.find((a) => a.id === selectedAuditId)?.name ?? '')
					: (frameworks.find((f) => f.id === selectedFrameworkId)?.name ?? '');
			if (!controls.length) {
				controlsError = 'No assessable controls were found for this selection.';
			}
		} catch {
			controlsError = 'Could not load controls for this selection.';
		} finally {
			loadingControls = false;
		}
	}

	function setG(key: string, patch: Partial<GuidanceState>) {
		const prev = guidance[key] ?? { open: false, loading: false, html: '', error: '' };
		guidance = { ...guidance, [key]: { ...prev, ...patch } };
	}

	async function toggleControl(c: Control) {
		const existing = guidance[c.key];
		if (existing?.open) {
			setG(c.key, { open: false });
			return;
		}
		setG(c.key, { open: true });
		if (existing?.html || existing?.loading) return; // already have it / fetching
		if (!hasProvider) {
			setG(c.key, { error: 'No AI provider is configured. Ask an administrator to add a key.' });
			return;
		}
		setG(c.key, { loading: true, error: '' });
		try {
			const res = await fetch('/audit-evidence/guidance', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					control_ref: c.ref,
					control_name: c.name,
					control_description: c.description,
					typical_evidence: c.typical_evidence,
					framework: frameworkName,
					scope,
					provider: selectedProvider,
					model: resolvedModel
				})
			});
			const body = await res.json();
			if (!res.ok) {
				setG(c.key, { loading: false, error: body.error ?? 'AI guidance failed. Try again.' });
				return;
			}
			setG(c.key, { loading: false, html: body.html ?? '<p>No guidance returned.</p>' });
		} catch {
			setG(c.key, { loading: false, error: 'AI guidance failed. Try again.' });
		}
	}
</script>

<div class="space-y-6">
	<p class="text-sm text-gray-500 max-w-3xl">{m.auditEvidenceDescription()}</p>

	{#if !hasProvider}
		<div class="card p-4 preset-tonal-warning text-sm">
			No AI provider is configured yet. Ask an administrator to add an API key under
			<strong>Policy Builder &rarr; AI providers</strong>, then reload this page.
		</div>
	{/if}

	<!-- Step 1: scope + AI -->
	<section class="bg-white card border border-gray-200 p-6 space-y-5">
		<div class="flex items-center gap-3">
			<span class="flex items-center justify-center w-7 h-7 rounded-full bg-primary-500 text-white text-sm font-bold">1</span>
			<h2 class="text-lg font-semibold text-gray-900">Your scope &amp; AI model</h2>
		</div>

		<label class="label">
			<span class="label-text">Scoping document / technology scope</span>
			<textarea
				class="textarea"
				bind:value={scope}
				rows="5"
				placeholder="Paste the technologies and services in scope, e.g. &#10;- Azure SQL Database (PaaS), 4 databases&#10;- Microsoft Entra ID for identity&#10;- Azure Blob Storage&#10;- GitHub Enterprise for source control"
			></textarea>
			<span class="text-xs text-gray-400">
				<i class="fa-solid fa-lock mr-1"></i>Kept in your browser only and used as private context.
				The AI never repeats your scope &mdash; it only references the relevant service names.
			</span>
		</label>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
			<label class="label">
				<span class="label-text">AI provider</span>
				<select class="select" bind:value={selectedProvider} disabled={!hasProvider}>
					{#if !hasProvider}
						<option value="">No provider configured</option>
					{/if}
					{#each providers as p}
						<option value={p.id}>{p.label}</option>
					{/each}
				</select>
			</label>
			<label class="label">
				<span class="label-text">Model</span>
				{#if modelMode === 'preset'}
					<select class="select" bind:value={selectedModel} disabled={!hasProvider}>
						{#each currentProvider?.models ?? [] as mdl}
							<option value={mdl}>{mdl}</option>
						{/each}
					</select>
					<button
						type="button"
						class="text-xs text-primary-600 hover:underline mt-1 self-start"
						onclick={() => {
							modelMode = 'custom';
							customModel = selectedModel;
						}}>Use a custom model name</button
					>
				{:else}
					<input class="input" bind:value={customModel} placeholder="e.g. gemini-2.0-flash" />
					<button
						type="button"
						class="text-xs text-primary-600 hover:underline mt-1 self-start"
						onclick={() => (modelMode = 'preset')}>Choose from preset models</button
					>
				{/if}
			</label>
		</div>
	</section>

	<!-- Step 2: choose source -->
	<section class="bg-white card border border-gray-200 p-6 space-y-5">
		<div class="flex items-center gap-3">
			<span class="flex items-center justify-center w-7 h-7 rounded-full bg-primary-500 text-white text-sm font-bold">2</span>
			<h2 class="text-lg font-semibold text-gray-900">Choose the audit or framework</h2>
		</div>

		<div class="flex flex-wrap gap-4">
			<label class="flex items-center gap-2 text-sm">
				<input type="radio" class="radio" value="audit" bind:group={sourceType} />
				<span>Existing audit</span>
			</label>
			<label class="flex items-center gap-2 text-sm">
				<input type="radio" class="radio" value="framework" bind:group={sourceType} />
				<span>Framework library</span>
			</label>
		</div>

		<div class="flex flex-wrap items-end gap-3">
			{#if sourceType === 'audit'}
				<label class="label grow max-w-xl">
					<span class="label-text">Audit (compliance assessment)</span>
					<select class="select" bind:value={selectedAuditId}>
						<option value="" disabled>— Select an audit —</option>
						{#each audits as a}
							<option value={a.id}>{a.name}{a.framework ? ` — ${a.framework}` : ''}</option>
						{/each}
					</select>
				</label>
			{:else}
				<label class="label grow max-w-xl">
					<span class="label-text">Framework</span>
					<select class="select" bind:value={selectedFrameworkId}>
						<option value="" disabled>— Select a framework —</option>
						{#each frameworks as f}
							<option value={f.id}>{f.name}</option>
						{/each}
					</select>
				</label>
			{/if}
			<button
				type="button"
				class="btn preset-filled-primary-500"
				onclick={loadControls}
				disabled={!selectedSourceId || loadingControls}
			>
				{#if loadingControls}
					<i class="fa-solid fa-spinner fa-spin mr-2"></i>{m.loading()}...
				{:else}
					<i class="fa-solid fa-list-check mr-2"></i>Load controls
				{/if}
			</button>
		</div>

		{#if controlsError}
			<div class="card p-4 preset-tonal-error text-sm">{controlsError}</div>
		{/if}
	</section>

	<!-- Step 3: controls + guidance -->
	{#if controls.length}
		<section class="bg-white card border border-gray-200 p-6 space-y-4">
			<div class="flex items-center gap-3">
				<span class="flex items-center justify-center w-7 h-7 rounded-full bg-primary-500 text-white text-sm font-bold">3</span>
				<h2 class="text-lg font-semibold text-gray-900">Controls &amp; evidence guidance</h2>
			</div>

			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-sm text-gray-500">
					{filteredControls.length} of {controls.length} controls
					{#if loadedLabel}<span class="text-gray-400">&mdash; {loadedLabel}</span>{/if}
				</p>
				<input class="input max-w-xs" bind:value={search} placeholder="Search controls..." />
			</div>

			<div class="divide-y divide-gray-200 border-t border-gray-200">
				{#each filteredControls as c (c.key)}
					{@const g = guidance[c.key]}
					<div class="py-3">
						<button
							type="button"
							class="w-full flex items-start gap-3 text-left"
							onclick={() => toggleControl(c)}
						>
							<i
								class="fa-solid {g?.open ? 'fa-chevron-down' : 'fa-chevron-right'} text-gray-400 mt-1 w-3"
							></i>
							<span class="grow">
								<span class="font-medium text-gray-900">
									{#if c.ref}<span class="text-primary-700">{c.ref}</span> {/if}{c.name}
								</span>
								{#if c.description}
									<span class="block text-sm text-gray-500 mt-0.5 line-clamp-2">{c.description}</span>
								{/if}
							</span>
							{#if !g?.html && !g?.loading}
								<span class="btn btn-sm preset-tonal-primary shrink-0">
									<i class="fa-solid fa-wand-magic-sparkles mr-1"></i>Guidance
								</span>
							{/if}
						</button>

						{#if g?.open}
							<div class="ml-6 mt-3">
								{#if g.loading}
									<p class="text-sm text-gray-500">
										<i class="fa-solid fa-spinner fa-spin mr-2"></i>Generating evidence guidance...
									</p>
								{:else if g.error}
									<div class="card p-3 preset-tonal-error text-sm">{g.error}</div>
								{:else if g.html}
									<div class="evidence-guidance rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-800">
										{@html g.html}
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}
</div>

<style>
	.evidence-guidance :global(h1),
	.evidence-guidance :global(h2),
	.evidence-guidance :global(h3),
	.evidence-guidance :global(strong) {
		font-weight: 600;
		color: #111827;
	}
	.evidence-guidance :global(h2) {
		font-size: 1rem;
		margin: 0.8em 0 0.3em;
	}
	.evidence-guidance :global(h3) {
		font-size: 0.95rem;
		margin: 0.7em 0 0.25em;
	}
	.evidence-guidance :global(p) {
		margin: 0.4em 0;
		line-height: 1.55;
	}
	.evidence-guidance :global(ul),
	.evidence-guidance :global(ol) {
		padding-left: 1.3em;
		margin: 0.3em 0;
	}
	.evidence-guidance :global(ul) {
		list-style: disc;
	}
	.evidence-guidance :global(ol) {
		list-style: decimal;
	}
	.evidence-guidance :global(li) {
		margin: 0.2em 0;
	}
	.evidence-guidance :global(code) {
		background: #e5e7eb;
		padding: 0 0.3em;
		border-radius: 0.25em;
	}
</style>
