<script lang="ts">
	// Netlink Aegis - Word-like WYSIWYG editor for the Policy Builder.
	//
	// Framework-agnostic TipTap (@tiptap/core) mounted in onMount so it works
	// cleanly with Svelte 5 runes. The edited document is exposed as HTML via the
	// bindable `html` prop; the parent reads it for save + DOCX/PDF export.
	import { onMount, onDestroy } from 'svelte';
	import { Editor, Extension } from '@tiptap/core';
	import StarterKit from '@tiptap/starter-kit';
	import Underline from '@tiptap/extension-underline';
	import TextStyle from '@tiptap/extension-text-style';
	import Color from '@tiptap/extension-color';
	import Highlight from '@tiptap/extension-highlight';
	import TextAlign from '@tiptap/extension-text-align';
	import FontFamily from '@tiptap/extension-font-family';
	import Image from '@tiptap/extension-image';
	import Link from '@tiptap/extension-link';
	import Table from '@tiptap/extension-table';
	import TableRow from '@tiptap/extension-table-row';
	import TableHeader from '@tiptap/extension-table-header';
	import TableCell from '@tiptap/extension-table-cell';

	let { html = $bindable('<p></p>'), editable = true } = $props();

	// Custom font-size mark (TipTap v2 has no built-in font-size extension).
	const FontSize = Extension.create({
		name: 'fontSize',
		addOptions() {
			return { types: ['textStyle'] };
		},
		addGlobalAttributes() {
			return [
				{
					types: this.options.types,
					attributes: {
						fontSize: {
							default: null,
							parseHTML: (el: HTMLElement) => el.style.fontSize || null,
							renderHTML: (attrs: Record<string, string>) =>
								attrs.fontSize ? { style: `font-size: ${attrs.fontSize}` } : {}
						}
					}
				}
			];
		},
		addCommands() {
			return {
				setFontSize:
					(size: string) =>
					({ chain }: any) =>
						chain().setMark('textStyle', { fontSize: size }).run(),
				unsetFontSize:
					() =>
					({ chain }: any) =>
						chain().setMark('textStyle', { fontSize: null }).removeEmptyTextStyle().run()
			};
		}
	});

	const FONT_FAMILIES = [
		{ label: 'Default', value: '' },
		{ label: 'Arial', value: 'Arial, sans-serif' },
		{ label: 'Calibri', value: 'Calibri, sans-serif' },
		{ label: 'Georgia', value: 'Georgia, serif' },
		{ label: 'Times New Roman', value: '"Times New Roman", serif' },
		{ label: 'Verdana', value: 'Verdana, sans-serif' },
		{ label: 'Tahoma', value: 'Tahoma, sans-serif' },
		{ label: 'Trebuchet MS', value: '"Trebuchet MS", sans-serif' },
		{ label: 'Courier New', value: '"Courier New", monospace' }
	];
	const FONT_SIZES = ['10px', '11px', '12px', '14px', '16px', '18px', '24px', '30px', '36px'];

	let element: HTMLDivElement;
	let fileInput: HTMLInputElement;
	// IMPORTANT: $state.raw (not $state). A TipTap Editor wraps a ProseMirror
	// instance; deep-proxying it via $state corrupts ProseMirror and throws on
	// mount, which breaks hydration for the whole page. $state.raw keeps the
	// reference reactive (so {#if}/disabled update) without proxying internals.
	let editor = $state.raw<Editor | null>(null);
	let lastEmitted = '';
	let tick = $state(0);

	let mountError = $state('');

	onMount(() => {
		try {
		editor = new Editor({
			element,
			extensions: [
				StarterKit,
				Underline,
				TextStyle,
				Color,
				FontSize,
				FontFamily,
				Highlight.configure({ multicolor: true }),
				TextAlign.configure({ types: ['heading', 'paragraph'] }),
				Image.configure({ inline: false, allowBase64: true }),
				Link.configure({ openOnClick: false, autolink: true }),
				Table.configure({ resizable: true }),
				TableRow,
				TableHeader,
				TableCell
			],
			content: html || '<p></p>',
			editable,
			editorProps: {
				attributes: { class: 'policy-editor-content focus:outline-none' }
			},
			onTransaction: () => {
				tick += 1;
			},
			onUpdate: ({ editor }) => {
				lastEmitted = editor.getHTML();
				html = lastEmitted;
			}
		});
		} catch (e) {
			mountError = (e as Error)?.message || 'The editor failed to load.';
			console.error('RichTextEditor mount failed', e);
		}
	});

	onDestroy(() => editor?.destroy());

	$effect(() => {
		const incoming = html;
		if (editor && incoming !== lastEmitted) {
			lastEmitted = incoming;
			editor.commands.setContent(incoming || '<p></p>', false);
		}
	});

	function isActive(name: string, attrs: Record<string, unknown> = {}): boolean {
		void tick;
		return editor?.isActive(name, attrs) ?? false;
	}
	function inTable(): boolean {
		void tick;
		return editor?.isActive('table') ?? false;
	}

	const btnBase =
		'px-2 py-1 text-sm rounded text-gray-700 hover:bg-gray-200 transition-colors disabled:opacity-40';
	function cls(active: boolean): string {
		return active ? `${btnBase} bg-primary-500/15 text-primary-700` : btnBase;
	}

	function setFontFamily(v: string) {
		if (!editor) return;
		if (v) editor.chain().focus().setFontFamily(v).run();
		else editor.chain().focus().unsetFontFamily().run();
	}
	function setFontSize(v: string) {
		if (!editor) return;
		if (v) (editor.chain().focus() as any).setFontSize(v).run();
		else (editor.chain().focus() as any).unsetFontSize().run();
	}
	function setColor(e: Event) {
		const v = (e.target as HTMLInputElement).value;
		editor?.chain().focus().setColor(v).run();
	}
	function setHighlight(e: Event) {
		const v = (e.target as HTMLInputElement).value;
		editor?.chain().focus().toggleHighlight({ color: v }).run();
	}
	function addLink() {
		if (!editor) return;
		const prev = editor.getAttributes('link').href ?? '';
		const url = window.prompt('Link URL', prev);
		if (url === null) return;
		if (url === '') {
			editor.chain().focus().extendMarkRange('link').unsetLink().run();
			return;
		}
		editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
	}
	function pickImage() {
		fileInput?.click();
	}
	function onImageChosen(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file || !editor) return;
		if (!file.type.startsWith('image/')) return;
		if (file.size > 4 * 1024 * 1024) {
			window.alert('Image is too large (max 4 MB).');
			input.value = '';
			return;
		}
		const reader = new FileReader();
		reader.onload = () => {
			const src = reader.result as string;
			editor?.chain().focus().setImage({ src }).run();
		};
		reader.readAsDataURL(file);
		input.value = '';
	}
	function insertTable() {
		editor?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
	}
</script>

<div class="rich-text-editor border border-gray-200 rounded-lg overflow-hidden bg-white">
	{#if editable}
		<div class="flex flex-wrap items-center gap-1 p-2 border-b border-gray-200 bg-gray-50">
			<!-- Paragraph style -->
			<select
				class="text-sm rounded border border-gray-200 bg-white px-1 py-1"
				title="Paragraph style"
				onchange={(e) => {
					const v = (e.target as HTMLSelectElement).value;
					if (v === 'p') editor?.chain().focus().setParagraph().run();
					else
						editor
							?.chain()
							.focus()
							.toggleHeading({ level: Number(v) as 1 | 2 | 3 })
							.run();
				}}
			>
				<option value="p" selected={isActive('paragraph')}>Normal</option>
				<option value="1" selected={isActive('heading', { level: 1 })}>Heading 1</option>
				<option value="2" selected={isActive('heading', { level: 2 })}>Heading 2</option>
				<option value="3" selected={isActive('heading', { level: 3 })}>Heading 3</option>
			</select>

			<!-- Font family -->
			<select
				class="text-sm rounded border border-gray-200 bg-white px-1 py-1 max-w-[8rem]"
				title="Font"
				onchange={(e) => setFontFamily((e.target as HTMLSelectElement).value)}
			>
				{#each FONT_FAMILIES as f}
					<option value={f.value}>{f.label}</option>
				{/each}
			</select>

			<!-- Font size -->
			<select
				class="text-sm rounded border border-gray-200 bg-white px-1 py-1"
				title="Font size"
				onchange={(e) => setFontSize((e.target as HTMLSelectElement).value)}
			>
				<option value="">Size</option>
				{#each FONT_SIZES as s}
					<option value={s}>{s.replace('px', '')}</option>
				{/each}
			</select>

			<span class="mx-1 w-px self-stretch bg-gray-300"></span>

			<button type="button" class="{cls(isActive('bold'))} font-bold" onclick={() => editor?.chain().focus().toggleBold().run()} title="Bold">B</button>
			<button type="button" class={cls(isActive('italic'))} onclick={() => editor?.chain().focus().toggleItalic().run()} title="Italic"><span class="italic">I</span></button>
			<button type="button" class={cls(isActive('underline'))} onclick={() => editor?.chain().focus().toggleUnderline().run()} title="Underline"><span class="underline">U</span></button>
			<button type="button" class={cls(isActive('strike'))} onclick={() => editor?.chain().focus().toggleStrike().run()} title="Strikethrough"><span class="line-through">S</span></button>

			<!-- Text color -->
			<label class="px-1 py-1 rounded hover:bg-gray-200 cursor-pointer flex items-center" title="Text color">
				<i class="fa-solid fa-a text-sm"></i>
				<input type="color" class="w-4 h-4 ml-0.5 border-0 bg-transparent cursor-pointer p-0" oninput={setColor} />
			</label>
			<!-- Highlight color -->
			<label class="px-1 py-1 rounded hover:bg-gray-200 cursor-pointer flex items-center" title="Highlight">
				<i class="fa-solid fa-highlighter text-sm"></i>
				<input type="color" class="w-4 h-4 ml-0.5 border-0 bg-transparent cursor-pointer p-0" value="#fff59d" oninput={setHighlight} />
			</label>

			<span class="mx-1 w-px self-stretch bg-gray-300"></span>

			<!-- Alignment -->
			<button type="button" class={cls(isActive({ textAlign: 'left' }))} onclick={() => editor?.chain().focus().setTextAlign('left').run()} title="Align left"><i class="fa-solid fa-align-left"></i></button>
			<button type="button" class={cls(isActive({ textAlign: 'center' }))} onclick={() => editor?.chain().focus().setTextAlign('center').run()} title="Align center"><i class="fa-solid fa-align-center"></i></button>
			<button type="button" class={cls(isActive({ textAlign: 'right' }))} onclick={() => editor?.chain().focus().setTextAlign('right').run()} title="Align right"><i class="fa-solid fa-align-right"></i></button>
			<button type="button" class={cls(isActive({ textAlign: 'justify' }))} onclick={() => editor?.chain().focus().setTextAlign('justify').run()} title="Justify"><i class="fa-solid fa-align-justify"></i></button>

			<span class="mx-1 w-px self-stretch bg-gray-300"></span>

			<!-- Lists / blocks -->
			<button type="button" class={cls(isActive('bulletList'))} onclick={() => editor?.chain().focus().toggleBulletList().run()} title="Bullet list"><i class="fa-solid fa-list-ul"></i></button>
			<button type="button" class={cls(isActive('orderedList'))} onclick={() => editor?.chain().focus().toggleOrderedList().run()} title="Numbered list"><i class="fa-solid fa-list-ol"></i></button>
			<button type="button" class={cls(isActive('blockquote'))} onclick={() => editor?.chain().focus().toggleBlockquote().run()} title="Quote"><i class="fa-solid fa-quote-right"></i></button>
			<button type="button" class={cls(isActive('codeBlock'))} onclick={() => editor?.chain().focus().toggleCodeBlock().run()} title="Code block"><i class="fa-solid fa-code"></i></button>
			<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().setHorizontalRule().run()} title="Divider"><i class="fa-solid fa-minus"></i></button>

			<span class="mx-1 w-px self-stretch bg-gray-300"></span>

			<!-- Insert -->
			<button type="button" class={cls(isActive('link'))} onclick={addLink} title="Insert / edit link"><i class="fa-solid fa-link"></i></button>
			<button type="button" class={cls(false)} onclick={pickImage} title="Insert image / logo"><i class="fa-solid fa-image"></i></button>
			<button type="button" class={cls(false)} onclick={insertTable} title="Insert table"><i class="fa-solid fa-table"></i></button>

			<span class="mx-1 w-px self-stretch bg-gray-300"></span>

			<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().undo().run()} disabled={!editor?.can().undo()} title="Undo"><i class="fa-solid fa-rotate-left"></i></button>
			<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().redo().run()} disabled={!editor?.can().redo()} title="Redo"><i class="fa-solid fa-rotate-right"></i></button>

			<input bind:this={fileInput} type="file" accept="image/*" class="hidden" onchange={onImageChosen} />
		</div>

		<!-- Contextual table toolbar -->
		{#if inTable()}
			<div class="flex flex-wrap items-center gap-1 px-2 py-1.5 border-b border-gray-200 bg-gray-100 text-xs">
				<span class="text-gray-500 mr-1">Table:</span>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().addColumnBefore().run()}>+Col before</button>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().addColumnAfter().run()}>+Col after</button>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().deleteColumn().run()}>Del col</button>
				<span class="mx-1 w-px self-stretch bg-gray-300"></span>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().addRowBefore().run()}>+Row before</button>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().addRowAfter().run()}>+Row after</button>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().deleteRow().run()}>Del row</button>
				<span class="mx-1 w-px self-stretch bg-gray-300"></span>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().toggleHeaderRow().run()}>Header row</button>
				<button type="button" class={cls(false)} onclick={() => editor?.chain().focus().mergeOrSplit().run()}>Merge/split</button>
				<button type="button" class="{btnBase} text-red-600" onclick={() => editor?.chain().focus().deleteTable().run()}>Delete table</button>
			</div>
		{/if}
	{/if}

	{#if mountError}
		<div class="p-3 text-sm text-red-700 bg-red-50 border-b border-red-200">
			Rich editor unavailable ({mountError}). You can still edit the HTML below and download/save.
		</div>
		<textarea
			class="w-full min-h-[340px] px-6 py-5 font-mono text-sm text-gray-900 focus:outline-none"
			bind:value={html}
		></textarea>
	{/if}
	<div
		bind:this={element}
		class="policy-editor-host max-h-[65vh] min-h-[340px] overflow-y-auto bg-white px-6 py-5 text-gray-900"
		class:hidden={mountError}
	></div>
</div>

<style>
	.policy-editor-host :global(.policy-editor-content) {
		min-height: 320px;
	}
	.policy-editor-host :global(h1) {
		font-size: 1.6rem;
		font-weight: 700;
		margin: 0.2em 0 0.5em;
	}
	.policy-editor-host :global(h2) {
		font-size: 1.3rem;
		font-weight: 700;
		margin: 1em 0 0.4em;
	}
	.policy-editor-host :global(h3) {
		font-size: 1.1rem;
		font-weight: 600;
		margin: 0.8em 0 0.3em;
	}
	.policy-editor-host :global(p) {
		margin: 0.4em 0;
		line-height: 1.6;
	}
	.policy-editor-host :global(ul) {
		list-style: disc;
		padding-left: 1.5em;
		margin: 0.4em 0;
	}
	.policy-editor-host :global(ol) {
		list-style: decimal;
		padding-left: 1.5em;
		margin: 0.4em 0;
	}
	.policy-editor-host :global(a) {
		color: #1d4ed8;
		text-decoration: underline;
	}
	.policy-editor-host :global(img) {
		max-width: 100%;
		height: auto;
		display: inline-block;
	}
	.policy-editor-host :global(blockquote) {
		border-left: 3px solid #cbd5e1;
		color: #475569;
		padding-left: 1em;
		margin: 0.6em 0;
	}
	.policy-editor-host :global(pre) {
		background: #f1f5f9;
		padding: 0.75em 1em;
		border-radius: 0.4em;
		overflow-x: auto;
	}
	.policy-editor-host :global(hr) {
		margin: 1em 0;
		border: none;
		border-top: 1px solid #e2e8f0;
	}
	.policy-editor-host :global(table) {
		border-collapse: collapse;
		width: 100%;
		margin: 0.6em 0;
		table-layout: fixed;
	}
	.policy-editor-host :global(th),
	.policy-editor-host :global(td) {
		border: 1px solid #cbd5e1;
		padding: 6px 8px;
		vertical-align: top;
	}
	.policy-editor-host :global(th) {
		background: #f1f5f9;
		font-weight: 600;
	}
</style>
