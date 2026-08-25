<script lang="ts">
	let {
		viewMode,
		onViewModeChange
	}: {
		viewMode: '2d' | '3d';
		onViewModeChange: (mode: '2d' | '3d') => void;
	} = $props();
</script>

<div class="map-toolbar" role="region" aria-label="Map controls">
	<div class="control-header">
		<span class="control-kicker">Map Controls</span>
		<div class="view-toggle" role="group" aria-label="Map view mode">
			<button
				class:active={viewMode === '3d'}
				aria-pressed={viewMode === '3d'}
				type="button"
				onclick={() => onViewModeChange('3d')}
			>
				3D
			</button>
			<button
				class:active={viewMode === '2d'}
				aria-pressed={viewMode === '2d'}
				type="button"
				onclick={() => onViewModeChange('2d')}
			>
				2D
			</button>
		</div>
	</div>
</div>

<style>
	.map-toolbar {
		position: fixed;
		top: 1rem;
		left: 1rem;
		z-index: 2;
		width: min(25rem, calc(100% - 2rem));
		overflow: hidden;
		border: 1px solid rgb(23 62 59 / 14%);
		border-radius: 0.9rem;
		background: var(--bg);
		box-shadow: 0 0.75rem 2rem rgb(30 56 55 / 18%);
	}

	.control-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1.5rem;
	}

	.control-kicker {
		color: var(--fg);
		font-size: 1.25rem;
		font-weight: 700;
	}

	.view-toggle {
		display: flex;
		gap: 0.5rem;
	}

	.view-toggle button {
		width: 36px;
		height: 36px;
		border: 1px solid rgb(23 62 59 / 14%);
		border-radius: 50%;
		background: transparent;
		color: #476563;
		font-size: 0.75rem;
		font-weight: 700;
	}

	.view-toggle button.active {
		background: var(--fg);
		color: var(--bg);
	}

	@media (max-width: 899px) {
		.map-toolbar {
			position: static;
			width: auto;
			margin-bottom: 3.5rem;
			border-radius: 1rem 1rem 0 0;
			border-bottom: none;
			box-shadow: none;
		}
	}
</style>
