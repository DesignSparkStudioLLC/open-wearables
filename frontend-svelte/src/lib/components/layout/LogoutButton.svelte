<script lang="ts">
	import LogOut from '@lucide/svelte/icons/log-out';

	let { onclick }: { onclick?: () => void } = $props();
</script>

<!-- Inert until auth lands: no session exists to end yet. Wiring it up means
     passing an `onclick` from the two call sites, nothing more. -->
<button
	type="button"
	{onclick}
	class="flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium
		text-muted-foreground transition-colors hover:bg-surface-muted hover:text-danger"
>
	<LogOut size={18} aria-hidden="true" />
	Logout
</button>
