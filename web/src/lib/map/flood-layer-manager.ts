import type { Map as MapLibreMap, PropertyValueSpecification } from 'maplibre-gl';

import { floodHazard, floodHazardColors } from '$lib/data/flood';
import { metroCityBounds } from '$lib/data/metro-boundary';

const fillColor = [
	'match',
	['get', 'Var'],
	1,
	floodHazardColors.Mild,
	2,
	floodHazardColors.Moderate,
	3,
	floodHazardColors.Severe,
	'#000000'
] as unknown as PropertyValueSpecification<string>;

export function addFloodLayer(map: MapLibreMap, firstSymbolLayerId?: string) {
	map.addSource('metro-manila-flood-5yr', {
		type: 'vector',
		tiles: [floodHazard.tilePath],
		minzoom: 10,
		maxzoom: 15,
		bounds: [...metroCityBounds]
	});
	map.addLayer(
		{
			id: 'metro-manila-flood-5yr',
			type: 'fill',
			source: 'metro-manila-flood-5yr',
			'source-layer': 'flood',
			paint: { 'fill-color': fillColor, 'fill-opacity': 0.8 }
		},
		firstSymbolLayerId
	);
}
