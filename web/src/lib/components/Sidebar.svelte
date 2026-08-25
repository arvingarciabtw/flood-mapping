<script lang="ts">
	import type { BarangayProperties } from '$lib/data/barangays';

	import { metroBarangayAttribution } from '$lib/data/barangays';
	import { floodHazard, floodHazardColors, floodHazardMetadata } from '$lib/data/flood';
	import Attribution from './Attribution.svelte';

	let {
		selectedArea,
		mobileSidebarOpen
	}: {
		selectedArea: BarangayProperties | null;
		mobileSidebarOpen: boolean;
	} = $props();

	const hazardClasses = ['Mild', 'Moderate', 'Severe'] as const;
</script>

<aside
	id="flood-information"
	class="sidebar"
	class:mobile-open={mobileSidebarOpen}
	tabindex="-1"
	aria-label="Flood information"
>
	<div class="sidebar-inner">
		<div class="brand-row">
			<div class="brand-link">
				<span>Crowdsourced Flood Map</span>
			</div>
		</div>

		<section class="info-card selection-card" aria-live="polite">
			{#if selectedArea}
				<h2>{selectedArea.name}</h2>
				<p class="area-city">{selectedArea.cityName}</p>
				<div class="summary-line">
					<span class="period-label">{floodHazard.shortName}</span>
					<span
						class="summary-dot"
						style={`background: ${selectedArea.floodHazard.summary === 'NoData' ? 'var(--gray)' : selectedArea.floodHazard.summary === 'Mixed' ? 'linear-gradient(90deg, ${floodHazardColors.Mild}, ${floodHazardColors.Severe})' : floodHazardColors[selectedArea.floodHazard.summary]}`}
					></span>
				</div>
				{#if selectedArea.floodHazard.classes.length > 0}
					<div class="period-classes">
						{#each selectedArea.floodHazard.classes as hazardClass (hazardClass)}
							<p>
								<span class="legend-swatch" style={`background: ${floodHazardColors[hazardClass]}`}
								></span>
								{hazardClass}
							</p>
						{/each}
					</div>
				{:else}
					<p class="no-data">No flood hazard data intersects this area.</p>
				{/if}
				<Attribution
					source={floodHazardMetadata.source}
					sourceUrl={floodHazardMetadata.sourceUrl}
				/>
			{:else}
				<h2>Select a barangay</h2>
				<p>
					Click a barangay on the map or search for one to inspect its 5-year flood hazard classes.
				</p>
				<p class="boundary-attribution">{metroBarangayAttribution}</p>
			{/if}
		</section>

		<section class="info-card active-layer">
			<h2>5-year flood hazard</h2>
			<p>
				The map shows the source-provided classification for a flood event with a 5% annual
				probability of occurrence.
			</p>
			<div class="legend" aria-label="Flood hazard legend">
				{#each hazardClasses as hazardClass (hazardClass)}
					<div>
						<span class="legend-swatch" style={`background: ${floodHazardColors[hazardClass]}`}
						></span>
						{hazardClass}
					</div>
				{/each}
			</div>
			<Attribution source={floodHazardMetadata.source} sourceUrl={floodHazardMetadata.sourceUrl} />
		</section>
	</div>
</aside>

<style>
	.sidebar {
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		border-left: 1px solid var(--gray);
		background: var(--bg);
		scrollbar-color: var(--gray) transparent;
	}

	.sidebar-inner {
		padding: 1.5rem;
	}

	.brand-row {
		display: flex;
		align-items: center;
		padding-bottom: 1.5rem;
	}

	.brand-link {
		display: inline-flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 1.5rem;
		font-weight: 700;
	}

	.info-card {
		padding: 1.5rem;
		border-radius: 0.75rem;
		background: var(--neutral-light);
	}

	.info-card + .info-card {
		margin-top: 1rem;
	}

	h2 {
		margin-bottom: 0.75rem;
		font-size: 1.4rem;
		font-weight: 700;
		line-height: 1.2;
	}

	.info-card p {
		color: var(--fg-secondary);
		font-size: 1rem;
	}

	.area-city {
		margin-top: -0.45rem;
		font-size: 0.9rem !important;
	}

	.summary-line {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 1rem;
	}

	.period-label {
		font-weight: 700;
	}

	.summary-dot {
		width: 0.8rem;
		height: 0.8rem;
		border-radius: 50%;
	}

	.period-classes {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.5rem;
		margin-top: 0.75rem;
	}

	.period-classes p,
	.legend div {
		display: grid;
		grid-template-columns: 24px 1fr;
		align-items: center;
		gap: 0.5rem;
		color: var(--fg-secondary);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem 1.5rem;
		margin-top: 1.5rem;
	}

	.legend-swatch {
		display: block;
		width: 1.5rem;
		height: 0.625rem;
		border-radius: 2rem;
	}

	.no-data,
	.boundary-attribution {
		margin-top: 1rem;
	}

	@media (max-width: 899px) {
		.sidebar {
			position: absolute;
			inset: auto 0 0;
			z-index: 10;
			max-height: 50dvh;
			border: 1px solid var(--gray);
			border-bottom: 0;
			border-radius: 1.25rem 1.25rem 0 0;
			box-shadow: 0 -1rem 2rem rgb(30 56 55 / 18%);
			transform: translateY(100%);
			visibility: hidden;
			transition:
				transform 220ms ease-out,
				visibility 0s linear 220ms;
		}

		.sidebar.mobile-open {
			transform: translateY(0);
			visibility: visible;
			transition:
				transform 220ms ease-out,
				visibility 0s linear 0s;
		}

		.sidebar-inner {
			padding: 1rem 1rem 5rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.sidebar {
			transition: none;
		}
	}

	@media (min-width: 900px) {
		.sidebar {
			height: 100%;
		}
	}
</style>
