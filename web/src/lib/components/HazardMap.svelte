<script lang="ts">
	import type { Map as MapLibreMap } from 'maplibre-gl';

	import type { BarangayProperties } from '$lib/data/barangays';
	import { loadMetroBarangays } from '$lib/data/barangays';
	import { metroCityBounds } from '$lib/data/metro-boundary';
	import { loadOpenFreeMapStyle, transformOpenFreeMapRequest } from '$lib/map/open-free-map-style';
	import { createBarangayLayerManager } from '$lib/map/barangay-layer-manager';
	import { addFloodLayer } from '$lib/map/flood-layer-manager';
	import {
		getPanBounds,
		restrictSymbolLayers,
		setupBaseMap,
		updateMapCamera
	} from '$lib/map/map-setup';
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { onMount } from 'svelte';

	let {
		selectedBarangayId = null,
		viewMode,
		onSelectArea
	}: {
		selectedBarangayId?: string | null;
		viewMode: '2d' | '3d';
		onSelectArea?: (area: BarangayProperties | null) => void;
	} = $props();

	let mapElement: HTMLDivElement;
	let mapReady = $state(false);
	let syncSelectedBarangay: (id: string | null) => void = () => {};
	let setCamera: (mode: '2d' | '3d') => void = () => {};
	let disposeBarangays = () => {};
	let map: MapLibreMap | undefined;

	$effect(() => {
		if (mapReady) syncSelectedBarangay(selectedBarangayId);
	});

	$effect(() => {
		if (mapReady) setCamera(viewMode);
	});

	onMount(() => {
		let disposed = false;

		const initialize = async () => {
			const [{ setWorkerUrl, Map: MapLibreMap }, barangays] = await Promise.all([
				import('maplibre-gl'),
				loadMetroBarangays()
			]);
			if (disposed) return;

			setWorkerUrl(workerUrl);
			const style = await loadOpenFreeMapStyle();
			if (disposed) return;

			const mapInstance = new MapLibreMap({
				container: mapElement,
				style,
				transformRequest: transformOpenFreeMapRequest,
				center: [121.02, 14.61],
				zoom: 11.2,
				pitch: 45,
				bearing: -12,
				maxPitch: 75,
				pitchWithRotate: true,
				attributionControl: { compact: true }
			});
			map = mapInstance;
			mapInstance.on('error', ({ error }) => console.error(`[MapLibre] ${error.message}`));

			mapInstance.once('load', () => {
				if (disposed) return;
				const baseMap = setupBaseMap(
					mapInstance,
					barangays.features.map((feature) => feature.properties.name)
				);
				addFloodLayer(mapInstance, baseMap.firstSymbolLayerId);
				const barangayLayers = createBarangayLayerManager({
					map: mapInstance,
					barangays,
					firstSymbolLayerId: baseMap.firstSymbolLayerId,
					onSelectArea
				});
				barangayLayers.addLayers();
				disposeBarangays = barangayLayers.dispose;
				syncSelectedBarangay = barangayLayers.syncSelection;
				restrictSymbolLayers(mapInstance);

				mapInstance.fitBounds(
					[
						[metroCityBounds[0], metroCityBounds[1]],
						[metroCityBounds[2], metroCityBounds[3]]
					],
					{ padding: 32, maxZoom: 12, duration: 0 }
				);
				mapInstance.setMaxBounds(getPanBounds(mapInstance));
				mapInstance.setMinZoom(mapInstance.getZoom());
				setCamera = (mode) => updateMapCamera(mapInstance, mode);
				setCamera(viewMode);
				mapReady = true;
			});
		};

		void initialize();

		return () => {
			disposed = true;
			disposeBarangays();
			map?.remove();
			map = undefined;
		};
	});
</script>

<div class="map-shell">
	<div
		bind:this={mapElement}
		class="map"
		data-map-ready={mapReady}
		role="region"
		aria-label="Interactive flood map of Manila, Pasig, and Marikina"
		aria-describedby="map-boundary-note"
	></div>
	<div id="map-boundary-note" class="boundary-note" role="note">
		UP NOAH 5-year modeled flood hazard layer. City and barangay boundaries are from OCHA
		Philippines COD-AB.
	</div>
</div>

<style>
	.map-shell {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 0;
		overflow: hidden;
		background: #d9e5e4;
		isolation: isolate;
	}

	.map {
		position: absolute;
		inset: 0;
	}

	.boundary-note {
		position: absolute;
		z-index: 2;
		bottom: 1rem;
		left: 1rem;
		max-width: 20rem;
		padding: 0.65rem 0.8rem;
		border: 1px solid rgb(255 255 255 / 55%);
		border-radius: 0.6rem;
		background: var(--bg);
		color: var(--fg);
		font-size: 0.875rem;
		box-shadow: 0 0.5rem 1.5rem rgb(30 56 55 / 12%);
	}

	@media (max-width: 899px) {
		.boundary-note {
			display: none;
		}
	}
</style>
