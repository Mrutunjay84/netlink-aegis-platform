<script lang="ts">
	import { enhance } from '$app/forms';
	import { m } from '$paraglide/messages';
	import RichTextEditor from '$lib/components/PolicyBuilder/RichTextEditor.svelte';

	let { data } = $props();

	interface ProviderInfo {
		id: string;
		label: string;
		models: string[];
		default_model: string;
	}

	const providers: ProviderInfo[] = data.config?.providers ?? [];
	const hasProvider = providers.length > 0;

	// Curated picklists. "Other (specify)" reveals a free-text input.
	const INDUSTRIES = [
		'Banking & Financial Services (BFSI)',
		'Insurance',
		'IT / Software / SaaS',
		'Healthcare & Life Sciences',
		'Manufacturing',
		'Retail & E-commerce',
		'Telecommunications',
		'Energy & Utilities',
		'Government & Public Sector',
		'Education',
		'Pharmaceuticals',
		'Logistics & Transportation',
		'Media & Entertainment',
		'Hospitality',
		'Professional Services'
	];
	const FRAMEWORKS = [
		'ISO/IEC 27001:2022',
		'ISO/IEC 27701',
		'SOC 2',
		'PCI DSS',
		'HIPAA',
		'GDPR',
		'NIST CSF',
		'NIST SP 800-53',
		'NIST SP 800-171',
		'CIS Controls v8',
		'ISO 22301',
		'RBI Cyber Security Framework',
		'SEBI CSCRF',
		'IRDAI Information & Cyber Security Guidelines',
		'DPDP Act 2023 (India)',
		'General best practice (no specific framework)'
	];
	const CUSTOM = '__custom__';

	// Generation inputs
	let topic = $state('');
	let additionalContext = $state('');
	let industrySel = $state('');
	let industryCustom = $state('');
	let frameworkSel = $state('');
	let frameworkCustom = $state('');

	let selectedProvider = $state(data.config?.default ?? (providers[0]?.id ?? ''));
	let modelMode = $state<'preset' | 'custom'>('preset');
	let selectedModel = $state('');
	let customModel = $state('');

	const currentProvider = $derived(providers.find((p) => p.id === selectedProvider));
	const resolvedIndustry = $derived(industrySel === CUSTOM ? industryCustom.trim() : industrySel);
	const resolvedFramework = $derived(
		frameworkSel === CUSTOM ? frameworkCustom.trim() : frameworkSel
	);
	const resolvedModel = $derived(modelMode === 'custom' ? customModel.trim() : selectedModel);

	// Keep the model selection valid when the provider changes.
	$effect(() => {
		const p = providers.find((x) => x.id === selectedProvider);
		if (p && modelMode === 'preset' && !p.models.includes(selectedModel)) {
			selectedModel = p.default_model || p.models[0] || '';
		}
	});

	// Workflow state
	let generating = $state(false);
	let saving = $state(false);
	let downloading = $state<'' | 'pdf' | 'docx'>('');
	let aiAvailable = $state(true);
	let draftError = $state('');
	let saveError = $state('');
	let exportError = $state('');

	// Editable draft (Step 2) - the editor works in HTML. Shown by default with a
	// starter structure; AI generation (optional) fills it in.
	const STARTER_HTML =
		'<h2>Purpose</h2><p></p><h2>Scope</h2><p></p><h2>Policy Statements</h2><p></p><h2>Roles and Responsibilities</h2><p></p><h2>Compliance and Enforcement</h2><p></p><h2>Review and Revision</h2><p></p>';
	let policyName = $state('');
	let policyHtml = $state(STARTER_HTML);
	let refId = $state('');
	let folder = $state('');

	// Result
	let savedUrl = $state('');
	let savedName = $state('');

	function safeFilename(name: string): string {
		return (name || 'policy').replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'policy';
	}

	async function downloadFile(format: 'pdf' | 'docx') {
		if (!policyHtml.trim() || downloading) return;
		downloading = format;
		exportError = '';
		try {
			const res = await fetch('/policy-builder/export', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ format, html: policyHtml, title: policyName })
			});
			if (!res.ok) {
				if (res.status === 401 || res.status === 403) {
					exportError = 'Your session has expired. Please log in again, then retry.';
				} else {
					const detail = await res.text().catch(() => '');
					exportError = `Could not generate the ${format.toUpperCase()} file (error ${res.status}). ${detail}`.trim();
				}
				return;
			}
			const blob = await res.blob();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `${safeFilename(policyName)}.${format}`;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (e) {
			exportError = `Could not generate the ${format.toUpperCase()} file: ${(e as Error)?.message ?? 'network error'}.`;
		} finally {
			downloading = '';
		}
	}

	// ---- Admin: AI provider settings ----------------------------------------
	let showSettings = $state(false);
	let savingSettings = $state(false);
	let settingsMessage = $state('');
	let aiSettings = $state(data.aiSettings);

</script>

<div class="space-y-6">
	<!-- Intro + admin entry -->
	<div class="flex items-start justify-between gap-4">
		<p class="text-sm text-gray-500 max-w-3xl">{m.policyBuilderDescription()}</p>
		{#if data.isAiAdmin}
			<button
				type="button"
				class="btn btn-sm preset-tonal-surface shrink-0"
				onclick={() => (showSettings = !showSettings)}
			>
				<i class="fa-solid fa-gear mr-2"></i>AI providers
			</button>
		{/if}
	</div>

	<!-- Admin: provider configuration -->
	{#if data.isAiAdmin && showSettings}
		<section class="bg-white card border border-primary-300 p-6 space-y-4">
			<div class="flex items-center gap-2">
				<i class="fa-solid fa-key text-primary-500"></i>
				<h2 class="text-lg font-semibold text-gray-900">AI provider settings</h2>
			</div>
			<p class="text-sm text-gray-500">
				Configure API keys for the providers you want to offer. Keys are stored securely on the
				server and never shown again. Leave a key blank to keep the existing one.
			</p>
			<form
				method="POST"
				action="?/saveSettings"
				use:enhance={() => {
					savingSettings = true;
					settingsMessage = '';
					return async ({ result }) => {
						savingSettings = false;
						if (result.type === 'success' && result.data?.settings) {
							aiSettings = result.data.settings;
							settingsMessage = 'Saved. Reload the page to use newly added providers.';
						} else if (result.type === 'failure') {
							settingsMessage =
								(result.data?.settingsError as string) ?? 'Could not save settings.';
						}
					};
				}}
			>
				<div class="space-y-4">
					{#each Object.entries(aiSettings?.providers ?? {}) as [pid, info]}
						<div class="grid grid-cols-1 md:grid-cols-2 gap-3 items-end border-b border-gray-200 pb-4">
							<div class="md:col-span-2 flex items-center gap-2">
								<span class="font-semibold text-gray-800">{info.label}</span>
								{#if info.configured}
									<span class="badge preset-tonal-success">Configured</span>
								{:else}
									<span class="badge preset-tonal-surface">Not set</span>
								{/if}
							</div>
							<label class="label">
								<span class="label-text">API key</span>
								<input
									class="input"
									type="password"
									name={`${pid}_api_key`}
									autocomplete="off"
									placeholder={info.configured ? '•••••••• (leave blank to keep)' : 'Paste API key'}
								/>
							</label>
							<label class="label">
								<span class="label-text">Base URL (optional override)</span>
								<input class="input" name={`${pid}_base_url`} value={info.base_url} placeholder={info.default_base_url} />
							</label>
						</div>
					{/each}

					<label class="label max-w-sm">
						<span class="label-text">Default provider</span>
						<select class="select" name="default_provider" value={aiSettings?.default_provider ?? ''}>
							<option value="">— Auto —</option>
							{#each Object.entries(aiSettings?.providers ?? {}) as [pid, info]}
								<option value={pid}>{info.label}</option>
							{/each}
						</select>
					</label>
				</div>

				<div class="flex items-center gap-3 mt-4">
					<button type="submit" class="btn preset-filled-primary-500" disabled={savingSettings}>
						{savingSettings ? `${m.loading()}...` : 'Save provider settings'}
					</button>
					{#if settingsMessage}
						<span class="text-sm text-gray-500">{settingsMessage}</span>
					{/if}
				</div>
			</form>
		</section>
	{/if}

	<!-- Step 1: describe the policy -->
	<section class="bg-white card border border-gray-200 p-6 space-y-5">
		<div class="flex items-center gap-3">
			<span class="flex items-center justify-center w-7 h-7 rounded-full bg-primary-500 text-white text-sm font-bold">1</span>
			<h2 class="text-lg font-semibold text-gray-900">Describe the policy</h2>
		</div>

		{#if !hasProvider}
			<div class="card p-4 preset-tonal-warning text-sm">
				No AI provider is configured yet.
				{#if data.isAiAdmin}
					Add an API key under <strong>AI providers</strong> (top right) to enable generation.
				{:else}
					Ask an administrator to add an AI provider API key.
				{/if}
			</div>
		{/if}

		<form
			method="POST"
			action="?/draft"
			use:enhance={() => {
				generating = true;
				draftError = '';
				savedUrl = '';
				saveError = '';
				exportError = '';
				return async ({ result }) => {
					generating = false;
					if (result.type === 'success' && result.data?.draft) {
						const d = result.data.draft as {
							name?: string;
							html?: string;
							markdown?: string;
							ai_available?: boolean;
							error?: string;
						};
						policyName = d.name ?? topic;
						// Don't wipe what's in the editor if generation returned nothing.
						policyHtml = d.html && d.html.trim() ? d.html : policyHtml;
						aiAvailable = d.ai_available !== false;
						if (d.error === 'generation_failed') {
							draftError =
								'The AI provider returned an error. Check the provider settings, model name, and API key, then try again.';
						}
					} else if (result.type === 'failure') {
						draftError = (result.data?.draftError as string) ?? 'Could not generate a draft.';
					}
				};
			}}
		>
			<input type="hidden" name="industry" value={resolvedIndustry} />
			<input type="hidden" name="framework" value={resolvedFramework} />
			<input type="hidden" name="provider" value={selectedProvider} />
			<input type="hidden" name="model" value={resolvedModel} />

			<div class="space-y-4">
				<label class="label">
					<span class="label-text">Policy topic <span class="text-error-500">*</span></span>
					<input
						class="input"
						name="topic"
						bind:value={topic}
						placeholder="e.g. Acceptable Use Policy, Remote Working Policy"
						required
					/>
				</label>

				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					<label class="label">
						<span class="label-text">Industry / sector</span>
						<select class="select" bind:value={industrySel}>
							<option value="">— Select —</option>
							{#each INDUSTRIES as ind}
								<option value={ind}>{ind}</option>
							{/each}
							<option value={CUSTOM}>Other (specify)</option>
						</select>
						{#if industrySel === CUSTOM}
							<input class="input mt-2" bind:value={industryCustom} placeholder="Enter your industry" />
						{/if}
					</label>

					<label class="label">
						<span class="label-text">Compliance framework</span>
						<select class="select" bind:value={frameworkSel}>
							<option value="">— Select —</option>
							{#each FRAMEWORKS as fw}
								<option value={fw}>{fw}</option>
							{/each}
							<option value={CUSTOM}>Other (specify)</option>
						</select>
						{#if frameworkSel === CUSTOM}
							<input class="input mt-2" bind:value={frameworkCustom} placeholder="Enter the framework" />
						{/if}
					</label>
				</div>

				<label class="label">
					<span class="label-text">Additional context (optional)</span>
					<textarea
						class="textarea"
						bind:value={additionalContext}
						rows="3"
						placeholder="Anything specific to include: tools, obligations, exceptions, tone..."
					></textarea>
				</label>

				<!-- Provider + model -->
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
			</div>

			<div class="flex items-center gap-3 mt-5">
				<button type="submit" class="btn preset-filled-primary-500" disabled={generating || !hasProvider}>
					{#if generating}
						<i class="fa-solid fa-spinner fa-spin mr-2"></i>{m.loading()}...
					{:else}
						<i class="fa-solid fa-wand-magic-sparkles mr-2"></i>Generate policy
					{/if}
				</button>
				{#if generating}
					<span class="text-sm text-gray-500">Drafting with AI, this can take a few seconds...</span>
				{/if}
			</div>

			{#if draftError}
				<div class="card p-4 preset-tonal-error text-sm mt-3">{draftError}</div>
			{/if}
		</form>
	</section>

	<!-- Step 2: write, edit, save, download (always visible) -->
	<section class="bg-white card border border-gray-200 p-6 space-y-5">
			<div class="flex items-center gap-3">
				<span class="flex items-center justify-center w-7 h-7 rounded-full bg-primary-500 text-white text-sm font-bold">2</span>
				<h2 class="text-lg font-semibold text-gray-900">Write, edit &amp; export</h2>
			</div>
			<p class="text-sm text-gray-500 -mt-2">
				Write your policy here, or use <strong>Generate policy</strong> above to have AI draft it
				into this editor. Add your logo, tables and formatting just like in Word.
			</p>

			{#if !aiAvailable}
				<div class="card p-4 preset-tonal-warning text-sm">
					No draft was generated (AI unavailable). You can still write the policy in the editor
					below.
				</div>
			{/if}

			{#if savedUrl}
				<div class="card p-4 preset-tonal-success text-sm">
					Saved <strong>{savedName}</strong> to the policy register.
					<a class="anchor" href={savedUrl}>Open it</a>.
				</div>
			{/if}

			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<label class="label">
					<span class="label-text">{m.name()} <span class="text-error-500">*</span></span>
					<input class="input" bind:value={policyName} required />
				</label>
				<label class="label">
					<span class="label-text">Reference ID (optional)</span>
					<input class="input" bind:value={refId} placeholder="e.g. POL-AUP-001" />
				</label>
			</div>

			<div class="label">
				<span class="label-text">Policy document</span>
				<RichTextEditor bind:html={policyHtml} />
			</div>

			<!-- Downloads -->
			<div class="flex flex-wrap items-center gap-3">
				<button
					type="button"
					class="btn preset-outlined-surface-500"
					onclick={() => downloadFile('docx')}
					disabled={downloading !== ''}
				>
					{#if downloading === 'docx'}
						<i class="fa-solid fa-spinner fa-spin mr-2"></i>{m.loading()}...
					{:else}
						<i class="fa-solid fa-file-word mr-2 text-blue-600"></i>Download DOCX
					{/if}
				</button>
				<button
					type="button"
					class="btn preset-outlined-surface-500"
					onclick={() => downloadFile('pdf')}
					disabled={downloading !== ''}
				>
					{#if downloading === 'pdf'}
						<i class="fa-solid fa-spinner fa-spin mr-2"></i>{m.loading()}...
					{:else}
						<i class="fa-solid fa-file-pdf mr-2 text-red-600"></i>Download PDF
					{/if}
				</button>
				{#if exportError}
					<span class="text-sm text-error-500">{exportError}</span>
				{/if}
			</div>

			<!-- Save to register -->
			<form
				class="border-t border-gray-200 pt-5 space-y-4"
				method="POST"
				action="?/save"
				use:enhance={() => {
					saving = true;
					saveError = '';
					return async ({ result }) => {
						saving = false;
						if (result.type === 'success' && result.data?.saved) {
							const s = result.data.saved as { name?: string; url?: string };
							savedName = s.name ?? policyName;
							savedUrl = s.url ?? '';
						} else if (result.type === 'failure') {
							saveError = (result.data?.saveError as string) ?? 'Could not save the policy.';
						}
					};
				}}
			>
				<input type="hidden" name="name" value={policyName} />
				<input type="hidden" name="ref_id" value={refId} />
				<input type="hidden" name="description" value={policyHtml} />

				<div class="flex flex-wrap items-end gap-3">
					<label class="label">
						<span class="label-text">{m.domain()} <span class="text-error-500">*</span></span>
						<select class="select" name="folder" bind:value={folder} required>
							<option value="" disabled>—</option>
							{#each data.folders as f}
								<option value={f.id}>{f.name}</option>
							{/each}
						</select>
					</label>
					<button type="submit" class="btn preset-filled-primary-500" disabled={saving}>
						{#if saving}
							<i class="fa-solid fa-spinner fa-spin mr-2"></i>{m.loading()}...
						{:else}
							<i class="fa-solid fa-floppy-disk mr-2"></i>Save to policy register
						{/if}
					</button>
				</div>

				{#if saveError}
					<div class="card p-4 preset-tonal-error text-sm">{saveError}</div>
				{/if}
			</form>
	</section>
</div>
