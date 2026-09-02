<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { cn } from '$lib/utils/cn';
	import type { NavItem } from '$lib/config/nav';

	let {
		item,
		active = false,
		onnavigate
	}: {
		item: NavItem;
		active?: boolean;
		onnavigate?: () => void;
	} = $props();

	const Icon = $derived(item.icon);
</script>

<!-- Internal hrefs are already passed through resolve() in $lib/config/nav; the
     rule cannot see through a dynamic value. -->
<!-- eslint-disable svelte/no-navigation-without-resolve -->
<a
	href={item.href}
	target={item.external ? '_blank' : undefined}
	rel={item.external ? 'noreferrer' : undefined}
	aria-current={active ? 'page' : undefined}
	onclick={onnavigate}
	class={cn(
		'flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors',
		active
			? 'bg-primary/10 text-primary'
			: 'text-muted-foreground hover:bg-surface-muted hover:text-foreground'
	)}
>
	<Icon size={18} aria-hidden="true" />
	<span class="flex-1">{item.label}</span>
	{#if item.external}
		<ExternalLink size={14} aria-hidden="true" class="opacity-60" />
	{/if}
</a>
