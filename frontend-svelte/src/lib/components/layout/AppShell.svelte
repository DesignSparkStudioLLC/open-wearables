<script lang="ts">
	import type { Snippet } from 'svelte';
	import Sidebar from './Sidebar.svelte';
	import TopBar from './TopBar.svelte';
	import BottomNav from './BottomNav.svelte';

	let { children }: { children: Snippet } = $props();
</script>

<!-- dvh, not vh: on mobile browsers vh is the viewport *without* the collapsing
     address bar, which leaves a gap or a scroll jump as the bar hides. -->
<div class="min-h-dvh">
	<Sidebar />

	<div class="lg:pl-64">
		<TopBar />

		<!-- Bottom padding clears the fixed bottom bar (3.5rem) plus the home
		     indicator inset; on lg the bar is gone and normal spacing applies. -->
		<main
			class="mx-auto w-full max-w-6xl px-4 py-5 pb-[calc(4.5rem+env(safe-area-inset-bottom))]
				sm:px-6 lg:pb-10"
		>
			{@render children()}
		</main>
	</div>

	<BottomNav />
</div>
