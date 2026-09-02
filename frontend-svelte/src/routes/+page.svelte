<!-- Temporary theme check. Replace with the real landing/redirect once routing
     is in place; it exists only to verify the tokens in src/app.css render in
     both light and dark. -->
<script lang="ts">
	const swatches = [
		{ name: 'background', class: 'bg-background' },
		{ name: 'surface', class: 'bg-surface' },
		{ name: 'surface-muted', class: 'bg-surface-muted' },
		{ name: 'primary', class: 'bg-primary' },
		{ name: 'success', class: 'bg-success' },
		{ name: 'warning', class: 'bg-warning' },
		{ name: 'danger', class: 'bg-danger' }
	];
</script>

<main class="mx-auto max-w-2xl p-6">
	<h1 class="text-2xl font-semibold tracking-tight">Theme check</h1>
	<p class="text-muted-foreground mt-1 text-sm">
		Follows your OS setting. Switch light/dark to verify both.
	</p>

	<div class="border-border bg-surface mt-6 rounded-xl border p-4">
		<p class="text-foreground text-sm">Surface with foreground text.</p>
		<p class="text-muted-foreground mt-1 text-sm">Muted foreground text.</p>
		<button
			class="bg-primary text-primary-foreground hover:bg-primary-hover mt-4 rounded-lg px-4 py-2
				text-sm font-medium transition-colors"
		>
			Primary action
		</button>
	</div>

	<ul class="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
		{#each swatches as swatch (swatch.name)}
			<li>
				<div class="border-border h-14 rounded-lg border {swatch.class}"></div>
				<span class="text-muted-foreground mt-1 block text-xs">{swatch.name}</span>
			</li>
		{/each}
	</ul>
</main>
