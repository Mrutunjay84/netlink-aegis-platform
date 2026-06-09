<script lang="ts">
	import { enhance } from '$app/forms';
	import { m } from '$paraglide/messages';

	let { data } = $props();

	// Generation inputs
	let topic = $state('');

	// Workflow state
	let generating = $state(false);
	let saving = $state(false);
	let draftReady = $state(false);
	let aiAvailable = $state(true);
	let draftError = $state('');
	let saveError = $state('');

	// Editable draft (Step 2)
	let policyName = $state('');
	let policyBody = $state('');
	let refId = $state('');
	let folder = $state('');

	// Result
	let savedUrl = $state('');
	let savedName = $state('');
</script>

<div class="p-4 space-y-6">
	<header class="space-y-1">
		<h1 class="h2 font-bold">{m.policyBuilder()}</h1>
		<p class="text-surface-600-300-token">{m.policyBuilderDescription()}</p>
	</header>

	<!-- Step 1: describe the policy -->
	<section class="card p-4 space-y-4">
		<h2 class="h4 font-semibold">1. Describe the policy</h2>
		<form
			method="POST"
			action="?/draft"
			use:enhance={() => {
				generating = true;
				draftError = '';
				savedUrl = '';
				saveError = '';
				return async ({ result }) => {
					generating = false;
					if (result.type === 'success' && result.data?.draft) {
						const d = result.data.draft as {
							name?: string;
							description?: string;
							ai_available?: boolean;
							error?: string;
						};
						policyName = d.name ?? topic;
						policyBody = d.description ?? '';
						aiAvailable = d.ai_available !== false;
						if (d.error === 'generation_failed') {
							draftError =
								'The AI provider returned an error. Check the LLM settings, or write the policy manually below.';
						}
						draftReady = true;
					} else if (result.type === 'failure') {
						draftError = (result.data?.draftError as string) ?? 'Could not generate a draft.';
					}
				};
			}}
		>
			<label class="label">
				<span>Policy topic <span class="text-error-500">*</span></span>
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
					<span>Intended audience (optional)</span>
					<input class="input" name="audience" placeholder="e.g. All employees and contractors" />
				</label>
				<label class="label">
					<span>Align to standard / framework (optional)</span>
					<input class="input" name="framework" placeholder="e.g. ISO/IEC 27001:2022" />
				</label>
			</div>

			<label class="label">
				<span>Additional context (optional)</span>
				<textarea
					class="textarea"
					name="additional_context"
					rows="3"
					placeholder="Anything specific to include: tools, obligations, exceptions, tone..."
				></textarea>
			</label>

			<div class="flex items-center gap-3">
				<button type="submit" class="btn variant-filled-primary" disabled={generating}>
					{#if generating}
						{m.loading()}...
					{:else}
						Generate draft
					{/if}
				</button>
				{#if generating}
					<span class="text-sm text-surface-600-300-token">Drafting with AI, this can take a few seconds...</span>
				{/if}
			</div>

			{#if draftError}
				<aside class="alert variant-soft-error">
					<div class="alert-message">{draftError}</div>
				</aside>
			{/if}
		</form>
	</section>

	<!-- Step 2: review, edit, save -->
	{#if draftReady}
		<section class="card p-4 space-y-4">
			<h2 class="h4 font-semibold">2. Review &amp; save</h2>

			{#if !aiAvailable}
				<aside class="alert variant-soft-warning">
					<div class="alert-message">
						No AI provider is configured yet, so no draft was generated. You can still write the
						policy manually below. To enable AI drafting, set an LLM provider in Global Settings
						(recommended: an OpenAI-compatible API such as Gemini Flash).
					</div>
				</aside>
			{/if}

			{#if savedUrl}
				<aside class="alert variant-soft-success">
					<div class="alert-message">
						Saved <strong>{savedName}</strong> as a policy.
						<a class="anchor" href={savedUrl}>Open it</a>.
					</div>
				</aside>
			{/if}

			<form
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
				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					<label class="label">
						<span>{m.name()} <span class="text-error-500">*</span></span>
						<input class="input" name="name" bind:value={policyName} required />
					</label>
					<label class="label">
						<span>{m.domain()} <span class="text-error-500">*</span></span>
						<select class="select" name="folder" bind:value={folder} required>
							<option value="" disabled>—</option>
							{#each data.folders as f}
								<option value={f.id}>{f.name}</option>
							{/each}
						</select>
					</label>
				</div>

				<label class="label">
					<span>Reference ID (optional)</span>
					<input class="input" name="ref_id" bind:value={refId} placeholder="e.g. POL-AUP-001" />
				</label>

				<label class="label">
					<span>{m.description()}</span>
					<textarea class="textarea font-mono text-sm" name="description" bind:value={policyBody} rows="22"></textarea>
				</label>

				<div class="flex items-center gap-3">
					<button type="submit" class="btn variant-filled-primary" disabled={saving}>
						{#if saving}
							{m.loading()}...
						{:else}
							Save as policy
						{/if}
					</button>
				</div>

				{#if saveError}
					<aside class="alert variant-soft-error">
						<div class="alert-message">{saveError}</div>
					</aside>
				{/if}
			</form>
		</section>
	{/if}
</div>
