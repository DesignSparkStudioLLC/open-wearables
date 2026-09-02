<script lang="ts">
	import { page } from '$app/state';
	import { NAV_ITEMS, isNavItemActive } from '$lib/config/nav';

	// Derived from the nav config rather than passed down per page, so a new
	// destination gets a title without touching every route.
	const sectionTitle = $derived(
		NAV_ITEMS.find((item) => isNavItemActive(item, page.url.pathname))?.label ?? ''
	);
</script>

<header
	class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4
		backdrop-blur-md sm:px-6"
>
	<div class="flex items-center gap-2 lg:hidden">
		<span class="size-2.5 rounded-full bg-primary"></span>
		<span class="text-sm font-semibold tracking-tight">Open Wearables</span>
	</div>

	<h1 class="hidden text-sm font-semibold tracking-tight lg:block">{sectionTitle}</h1>
</header>
