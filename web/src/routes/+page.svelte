<script lang="ts">
	import type { BarangayCollection, BarangayProperties } from '$lib/data/barangays';

	import { searchMetroBarangays, loadMetroBarangays } from '$lib/data/barangays';
	import HazardMap from '$lib/components/HazardMap.svelte';
	import MapControls from '$lib/components/MapControls.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import { onMount } from 'svelte';

	let selectedArea = $state<BarangayProperties | null>(null);
	let selectedBarangayId = $state<string | null>(null);
	let barangayQuery = $state('');
	let barangaySearchOpen = $state(false);
	let highlightedBarangayIndex = $state(0);
	let barangays = $state<BarangayCollection | null>(null);
	let barangaySearchInput: HTMLInputElement;
	let barangaySearchBlurTimeout: ReturnType<typeof setTimeout> | undefined;
	let viewMode = $state<'2d' | '3d'>('3d');
	let mobileSidebarOpen = $state(false);
	let mobileControlsOpen = $state(false);
	let barangayMatches = $derived(
		barangays ? searchMetroBarangays(barangays, barangayQuery).slice(0, 8) : []
	);

	function updateSelectedArea(area: BarangayProperties | null) {
		selectedArea = area;
		selectedBarangayId = area?.id ?? null;
		barangayQuery = area?.name ?? '';
		barangaySearchOpen = false;
		highlightedBarangayIndex = 0;
	}

	function handleSearchInput(event: Event) {
		if (barangaySearchBlurTimeout) clearTimeout(barangaySearchBlurTimeout);
		barangayQuery = (event.currentTarget as HTMLInputElement).value;
		barangaySearchOpen = true;
		highlightedBarangayIndex = 0;
	}

	function handleSearchFocus() {
		barangaySearchOpen = barangayMatches.length > 0;
	}

	function handleSearchFocusOut(event: FocusEvent) {
		const search = event.currentTarget;
		const nextTarget = event.relatedTarget;
		if (search instanceof HTMLElement && nextTarget instanceof Node && search.contains(nextTarget))
			return;
		if (barangaySearchBlurTimeout) clearTimeout(barangaySearchBlurTimeout);
		barangaySearchBlurTimeout = setTimeout(() => (barangaySearchOpen = false), 100);
	}

	function selectSearchBarangay(area: BarangayProperties) {
		updateSelectedArea(area);
		barangaySearchInput?.focus();
	}

	function handleSearchKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			barangaySearchOpen = false;
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			barangaySearchOpen = true;
			highlightedBarangayIndex = Math.min(
				highlightedBarangayIndex + 1,
				Math.max(barangayMatches.length - 1, 0)
			);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			highlightedBarangayIndex = Math.max(highlightedBarangayIndex - 1, 0);
			return;
		}
		if (event.key === 'Enter' && barangaySearchOpen && barangayMatches.length > 0) {
			event.preventDefault();
			selectSearchBarangay(barangayMatches[highlightedBarangayIndex]);
		}
	}

	function toggleMobileSidebar() {
		mobileSidebarOpen = !mobileSidebarOpen;
		mobileControlsOpen = false;
	}

	function toggleMobileControls() {
		mobileControlsOpen = !mobileControlsOpen;
		mobileSidebarOpen = false;
	}

	onMount(() => {
		loadMetroBarangays()
			.then((data) => (barangays = data))
			.catch(() => (barangays = null));
		return () => {
			if (barangaySearchBlurTimeout) clearTimeout(barangaySearchBlurTimeout);
		};
	});
</script>

<svelte:head>
	<title>Crowdsourced Flood Map</title>
	<meta
		name="description"
		content="A 5-year modeled flood hazard map for Manila, Pasig, and Marikina."
	/>
</svelte:head>

<div class="app-shell">
	<section class="map-pane" aria-label="Flood map">
		<HazardMap {selectedBarangayId} {viewMode} onSelectArea={updateSelectedArea} />

		<section
			class="map-search"
			data-search-ready={barangays !== null}
			onfocusout={handleSearchFocusOut}
		>
			<input
				bind:this={barangaySearchInput}
				id="barangay-search"
				autocomplete="off"
				spellcheck="false"
				value={barangayQuery}
				placeholder="Find a barangay..."
				role="combobox"
				aria-autocomplete="list"
				aria-controls={barangaySearchOpen && barangayQuery.trim()
					? 'barangay-search-results'
					: undefined}
				aria-expanded={barangaySearchOpen}
				aria-activedescendant={barangaySearchOpen && barangayMatches.length > 0
					? `barangay-result-${barangayMatches[highlightedBarangayIndex].id}`
					: undefined}
				oninput={handleSearchInput}
				onkeydown={handleSearchKeydown}
				onfocus={handleSearchFocus}
			/>
			{#if barangaySearchOpen && (barangayMatches.length > 0 || barangayQuery.trim())}
				<div
					id="barangay-search-results"
					class="search-results"
					role={barangayMatches.length > 0 ? 'listbox' : 'status'}
					aria-live="polite"
				>
					{#if barangayMatches.length > 0}
						{#each barangayMatches as barangay, index (barangay.id)}
							<button
								id={`barangay-result-${barangay.id}`}
								class:highlighted={highlightedBarangayIndex === index}
								class="search-result"
								role="option"
								aria-selected={selectedBarangayId === barangay.id}
								type="button"
								onclick={() => selectSearchBarangay(barangay)}
								onmouseenter={() => (highlightedBarangayIndex = index)}
							>
								{barangay.name}
								<span>{barangay.cityName.replace('City of ', '')}</span>
							</button>
						{/each}
					{:else}
						<p class="search-empty">No barangays found.</p>
					{/if}
				</div>
			{/if}
		</section>

		<div
			id="mobile-map-controls"
			class:mobile-open={mobileControlsOpen}
			class="mobile-controls-panel"
		>
			<MapControls {viewMode} onViewModeChange={(mode) => (viewMode = mode)} />
		</div>

		<div class="mobile-action-bar">
			<button
				class:open={mobileSidebarOpen}
				class="mobile-sidebar-toggle"
				type="button"
				aria-controls="flood-information"
				aria-expanded={mobileSidebarOpen}
				onclick={toggleMobileSidebar}
			>
				<span class="icon"
					>{#if mobileSidebarOpen}<ChevronDown />{:else}<ChevronUp />{/if}</span
				>
				<span>{mobileSidebarOpen ? 'Hide details' : 'Show details'}</span>
			</button>
			<button
				class:open={mobileControlsOpen}
				class="mobile-controls-toggle"
				type="button"
				aria-controls="mobile-map-controls"
				aria-expanded={mobileControlsOpen}
				onclick={toggleMobileControls}
			>
				<span class="icon"
					>{#if mobileControlsOpen}<ChevronDown />{:else}<ChevronUp />{/if}</span
				>
				<span>{mobileControlsOpen ? 'Hide controls' : 'Map controls'}</span>
			</button>
		</div>
	</section>

	<Sidebar {selectedArea} {mobileSidebarOpen} />
</div>

<style>
	.app-shell {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(22rem, 28rem);
		width: 100%;
		min-height: 0;
		flex: 1;
	}

	.map-pane {
		position: relative;
		min-width: 0;
		min-height: 0;
		background: var(--neutral-light);
	}

	.map-search {
		position: absolute;
		top: 1rem;
		left: 1rem;
		z-index: 3;
		width: min(20rem, calc(100% - 2rem));
	}

	@media (min-width: 1250px) {
		.map-search {
			left: auto;
			right: 1rem;
		}
	}

	.map-search input {
		width: 100%;
		border: none;
		border-radius: 2.5rem;
		padding: 0.75rem 1.25rem;
		color: var(--fg);
		font-size: 1rem;
	}

	.map-search input:focus-visible {
		outline: none;
	}

	.search-results {
		display: grid;
		gap: 0.2rem;
		max-height: 14rem;
		margin-top: 0.5rem;
		overflow-y: auto;
		padding: 0.25rem;
		border-radius: 1.5rem;
		background: var(--bg);
	}

	.search-result {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		border: 0;
		border-radius: 2.5rem;
		padding: 0.5rem 1rem;
		background: transparent;
		color: var(--fg);
		font-size: 1rem;
		text-align: left;
	}

	.search-result span {
		color: var(--fg-secondary);
		font-size: 0.75rem;
		white-space: nowrap;
	}

	.search-result:hover,
	.search-result.highlighted,
	.search-result:focus-visible {
		background: var(--neutral-light);
	}

	.search-empty {
		padding: 0.5rem 1rem;
		color: var(--fg-secondary);
		font-size: 1rem;
	}

	.mobile-action-bar {
		display: none;
	}

	.mobile-controls-panel {
		display: contents;
	}

	@media (max-width: 899px) {
		.app-shell {
			display: block;
			position: relative;
			height: 100dvh;
			overflow: hidden;
		}

		.map-pane {
			height: 100%;
		}

		.map-search {
			top: 0.75rem;
			left: 0.75rem;
			width: calc(100% - 1.5rem);
		}

		.mobile-controls-panel {
			display: block;
			position: absolute;
			inset: auto 0 0;
			z-index: 10;
			max-height: 50dvh;
			overflow-y: auto;
			border: 1px solid var(--gray);
			border-bottom: 0;
			border-radius: 1.25rem 1.25rem 0 0;
			background: var(--bg);
			box-shadow: 0 -1rem 2rem rgb(30 56 55 / 18%);
			transform: translateY(100%);
			visibility: hidden;
			transition:
				transform 220ms ease-out,
				visibility 0s linear 220ms;
		}

		.mobile-controls-panel.mobile-open {
			transform: translateY(0);
			visibility: visible;
			transition:
				transform 220ms ease-out,
				visibility 0s linear 0s;
		}

		.mobile-action-bar {
			position: absolute;
			bottom: 0.75rem;
			left: 50%;
			z-index: 12;
			display: flex;
			gap: 0.5rem;
			justify-content: center;
			width: max-content;
			max-width: calc(100% - 1.5rem);
			transform: translateX(-50%);
		}

		.mobile-sidebar-toggle,
		.mobile-controls-toggle {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			gap: 0.35rem;
			min-width: 8.5rem;
			border: 1px solid rgb(23 62 59 / 14%);
			border-radius: 999px;
			padding: 0.65rem 1rem;
			background: var(--fg);
			color: var(--bg);
			font-size: 0.8rem;
			font-weight: 700;
			box-shadow: 0 0.75rem 2rem rgb(30 56 55 / 24%);
		}

		.mobile-sidebar-toggle.open,
		.mobile-controls-toggle.open {
			background: var(--accent-dark);
		}

		.mobile-sidebar-toggle .icon,
		.mobile-controls-toggle .icon {
			width: 1rem;
			height: 1rem;
			margin-top: -0.5rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.mobile-controls-panel {
			transition: none;
		}
	}

	@media (min-width: 900px) {
		.app-shell,
		.map-pane {
			height: 100%;
		}
	}
</style>
