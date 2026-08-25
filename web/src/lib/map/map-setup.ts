import type {
	FilterSpecification,
	Map as MapLibreMap,
	PropertyValueSpecification,
	RasterDEMSourceSpecification
} from 'maplibre-gl';

import { metroCityBoundary, metroCityGeometry, metroCityMask } from '$lib/data/metro-boundary';

type MapInstance = MapLibreMap;
export type MapBounds = [[number, number], [number, number]];

const terrainAttribution =
	'Elevation data © Mapzen, sourced from USGS, NASA, and other contributors.';

export function getPanBounds(map: MapInstance): MapBounds {
	const visibleBounds = map.getBounds();
	const center = map.getCenter();
	const centerPoint = map.project(center);
	const leftPoint = map.unproject([centerPoint.x - 2, centerPoint.y]);
	const rightPoint = map.unproject([centerPoint.x + 2, centerPoint.y]);

	return [
		[visibleBounds.getWest() - (center.lng - leftPoint.lng), visibleBounds.getSouth()],
		[visibleBounds.getEast() + (rightPoint.lng - center.lng), visibleBounds.getNorth()]
	];
}

export function updateMapCamera(map: MapInstance, nextMode: '2d' | '3d') {
	const is3d = nextMode === '3d';
	map.setTerrain(is3d ? { source: 'metro-terrain', exaggeration: 1.15 } : null);

	if (is3d) {
		map.dragRotate.enable();
		map.touchZoomRotate.enableRotation();
	} else {
		map.dragRotate.disable();
		map.touchZoomRotate.disableRotation();
	}

	map.easeTo({ pitch: is3d ? 45 : 0, bearing: is3d ? -12 : 0, duration: 500 });
}

function dimBaseMapTransportLayers(map: MapInstance, barangayNames: readonly string[]) {
	const detailVisibility = [
		'interpolate',
		['linear'],
		['zoom'],
		13,
		0,
		15,
		1
	] as unknown as PropertyValueSpecification<number>;
	const excludeBarangayNames = [
		'!',
		[
			'any',
			['match', ['get', 'name'], barangayNames, true, false],
			['match', ['get', 'name:latin'], barangayNames, true, false]
		]
	] as unknown as FilterSpecification;

	for (const layer of map.getStyle().layers ?? []) {
		const styleLayer = layer as {
			source?: string;
			'source-layer'?: string;
			maxzoom?: number;
		};
		if (styleLayer.source !== 'openmaptiles') continue;

		const sourceLayer = styleLayer['source-layer'];
		if (sourceLayer === 'transportation') {
			if (layer.type === 'line') {
				const maxzoom = styleLayer.maxzoom ?? 24;
				if (maxzoom > 13) map.setLayerZoomRange(layer.id, 13, maxzoom);
				else map.setLayoutProperty(layer.id, 'visibility', 'none');
				map.setPaintProperty(layer.id, 'line-opacity', detailVisibility);
				map.setPaintProperty(layer.id, 'line-color', '#d9c8b7');
			} else if (layer.type === 'fill' || layer.type === 'symbol') {
				map.setLayoutProperty(layer.id, 'visibility', 'none');
			}
		}

		if (sourceLayer === 'transportation_name' && layer.type === 'symbol') {
			map.setLayoutProperty(layer.id, 'visibility', 'visible');
			map.setPaintProperty(layer.id, 'icon-opacity', 0);
		}

		if (layer.type === 'symbol') {
			map.setPaintProperty(layer.id, 'text-opacity', detailVisibility);
			map.setPaintProperty(layer.id, 'text-halo-width', detailVisibility);
		}

		if (sourceLayer === 'place' && layer.type === 'symbol') {
			map.setFilter(
				layer.id,
				layer.filter
					? (['all', layer.filter, excludeBarangayNames] as unknown as FilterSpecification)
					: excludeBarangayNames
			);
		}
	}
}

export function restrictSymbolLayers(map: MapInstance) {
	const withinBoundary = ['within', metroCityGeometry] as unknown as FilterSpecification;

	for (const layer of map.getStyle().layers ?? []) {
		if (layer.type !== 'symbol') continue;
		map.setFilter(
			layer.id,
			layer.filter
				? (['all', layer.filter, withinBoundary] as unknown as FilterSpecification)
				: withinBoundary
		);
	}
}

export function setupBaseMap(map: MapInstance, barangayNames: readonly string[]) {
	dimBaseMapTransportLayers(map, barangayNames);
	const firstSymbolLayerId = map.getStyle().layers?.find((layer) => layer.type === 'symbol')?.id;
	const terrainSource: RasterDEMSourceSpecification = {
		type: 'raster-dem',
		tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
		tileSize: 256,
		maxzoom: 15,
		encoding: 'terrarium',
		attribution: terrainAttribution
	};

	map.addSource('metro-terrain', terrainSource);
	map.addSource('metro-terrain-hillshade', terrainSource);
	map.addLayer(
		{
			id: 'metro-terrain-hillshade',
			type: 'hillshade',
			source: 'metro-terrain-hillshade',
			paint: {
				'hillshade-exaggeration': 0.18,
				'hillshade-shadow-color': '#756c5f',
				'hillshade-highlight-color': '#fffaf0'
			}
		},
		firstSymbolLayerId
	);

	map.addSource('metro-city-mask', { type: 'geojson', data: metroCityMask });
	map.addLayer(
		{
			id: 'metro-city-mask',
			type: 'fill',
			source: 'metro-city-mask',
			paint: { 'fill-color': '#f7f2e8', 'fill-opacity': 0.5 }
		},
		firstSymbolLayerId
	);

	map.addSource('metro-city-boundary', { type: 'geojson', data: metroCityBoundary });
	map.addLayer(
		{
			id: 'metro-city-boundary',
			type: 'line',
			source: 'metro-city-boundary',
			paint: { 'line-color': '#d18f38', 'line-width': 2, 'line-opacity': 0.9 }
		},
		firstSymbolLayerId
	);

	return { firstSymbolLayerId };
}
