<script lang="ts">
	import logo from '$lib/assets/logo.svg?raw';
	import { cn } from '$lib/utils/cn';

	let { class: className }: { class?: string } = $props();
</script>

<!-- Mark only. The logotype stacks "Open / Wearables" on two lines, which is
     unreadable in a 56px app bar — use Wordmark where there is vertical room.
     Inlined for the same reason as Wordmark: <img> cannot inherit currentColor. -->
<span class={cn('inline-block text-foreground [&>svg]:h-full [&>svg]:w-auto', className)}>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- static asset inlined at build time, never user input -->
	{@html logo}
</span>
