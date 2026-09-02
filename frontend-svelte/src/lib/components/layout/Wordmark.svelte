<script lang="ts">
	import logotype from '$lib/assets/logotype.svg?raw';
	import { cn } from '$lib/utils/cn';

	let { class: className }: { class?: string } = $props();
</script>

<!-- Inlined rather than used as an <img> src: the mark paints with
     currentColor, and an <img> would not inherit it. The asset is ours and
     resolved at build time, so {@html} carries no injection risk.
     Height comes from the caller; the SVG keeps its own aspect ratio. -->
<span class={cn('inline-block text-foreground [&>svg]:h-full [&>svg]:w-auto', className)}>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- static asset inlined at build time, never user input -->
	{@html logotype}
</span>
