import type { FeatureCollection, Point } from 'geojson';
import type { Map as MapLibreMap, MapMouseEvent, PropertyValueSpecification } from 'maplibre-gl';

import type { BarangayCollection, BarangayProperties } from '$lib/data/barangays';
import { metroBarangayLabelPoints } from '$lib/data/barangays';

type LayerMouseEvent = MapMouseEvent & {
	features?: Array<{ properties?: unknown }>;
};

type LabelPoints = FeatureCollection<Point, Pick<BarangayProperties, 'id' | 'name'>>;

export function getBarangayProperties(object: unknown): BarangayProperties | null {
	if (!object || typeof object !== 'object') return null;
	const properties = object as Partial<BarangayProperties>;
	if (
		typeof properties.id !== 'string' ||
		typeof properties.name !== 'string' ||
		typeof properties.cityName !== 'string'
	) {
		return null;
	}
	return properties as BarangayProperties;
}

export function getBarangayBounds(barangays: BarangayCollection, id: string) {
	const feature = barangays.features.find((item) => item.properties.id === id);
	if (!feature) return null;

	let west = Infinity;
	let south = Infinity;
	let east = -Infinity;
	let north = -Infinity;
	const visit = (value: unknown): void => {
		if (!Array.isArray(value)) return;
		if (typeof value[0] === 'number' && typeof value[1] === 'number') {
			west = Math.min(west, value[0]);
			south = Math.min(south, value[1]);
			east = Math.max(east, value[0]);
			north = Math.max(north, value[1]);
			return;
		}
		for (const child of value) visit(child);
	};
	visit(feature.geometry.coordinates);
	return Number.isFinite(west)
		? ([
				[west, south],
				[east, north]
			] as [[number, number], [number, number]])
		: null;
}

export function createBarangayLayerManager({
	map,
	barangays,
	barangayLabelPoints = metroBarangayLabelPoints,
	firstSymbolLayerId,
	onSelectArea
}: {
	map: MapLibreMap;
	barangays: BarangayCollection;
	barangayLabelPoints?: LabelPoints;
	firstSymbolLayerId?: string;
	onSelectArea?: (area: BarangayProperties | null) => void;
}) {
	let selectedId: string | null = null;

	const clearSelection = () => {
		if (selectedId)
			map.setFeatureState({ source: 'metro-barangays', id: selectedId }, { selected: false });
		map.setPaintProperty('metro-barangay-dim', 'fill-opacity', 0);
		selectedId = null;
		onSelectArea?.(null);
	};

	const selectBarangay = (properties: BarangayProperties) => {
		if (selectedId === properties.id) {
			clearSelection();
			return;
		}
		if (selectedId)
			map.setFeatureState({ source: 'metro-barangays', id: selectedId }, { selected: false });
		selectedId = properties.id;
		map.setFeatureState({ source: 'metro-barangays', id: selectedId }, { selected: true });
		map.setPaintProperty('metro-barangay-dim', 'fill-opacity', [
			'case',
			['boolean', ['feature-state', 'selected'], false],
			0,
			0.3
		] as unknown as PropertyValueSpecification<number>);
		onSelectArea?.(properties);
	};

	const syncSelection = (id: string | null) => {
		if (!id) {
			if (selectedId) clearSelection();
			return;
		}
		if (selectedId === id) return;
		const feature = barangays.features.find((item) => item.properties.id === id);
		if (!feature) return;
		selectBarangay(feature.properties);
		const bounds = getBarangayBounds(barangays, id);
		if (bounds) map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 650 });
	};

	const onClick = (event: LayerMouseEvent) => {
		const properties = getBarangayProperties(event.features?.[0]?.properties);
		if (properties) selectBarangay(properties);
	};
	const onMapClick = (event: MapMouseEvent) => {
		if (map.queryRenderedFeatures(event.point, { layers: ['metro-barangay-fill'] }).length === 0) {
			clearSelection();
		}
	};
	const onMouseEnter = () => (map.getCanvas().style.cursor = 'pointer');
	const onMouseLeave = () => (map.getCanvas().style.cursor = '');

	const addLayers = () => {
		map.addSource('metro-barangays', { type: 'geojson', data: barangays, promoteId: 'id' });
		map.addSource('metro-barangay-labels', {
			type: 'geojson',
			data: barangayLabelPoints,
			promoteId: 'id'
		});
		map.addLayer(
			{
				id: 'metro-barangay-dim',
				type: 'fill',
				source: 'metro-barangays',
				paint: { 'fill-color': '#000000', 'fill-opacity': 0 }
			},
			firstSymbolLayerId
		);
		map.addLayer(
			{
				id: 'metro-barangay-fill',
				type: 'fill',
				source: 'metro-barangays',
				paint: {
					'fill-color': '#f2994a',
					'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0, 0]
				}
			},
			firstSymbolLayerId
		);
		map.addLayer(
			{
				id: 'metro-barangay-boundaries',
				type: 'line',
				source: 'metro-barangays',
				paint: {
					'line-color': [
						'case',
						['boolean', ['feature-state', 'selected'], false],
						'#eb5757',
						'#6f8881'
					],
					'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.5, 1],
					'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 1, 0.8]
				}
			},
			firstSymbolLayerId
		);
		map.addLayer({
			id: 'metro-barangay-labels',
			type: 'symbol',
			source: 'metro-barangay-labels',
			minzoom: 11,
			layout: {
				'symbol-placement': 'point',
				'text-field': ['get', 'name'],
				'text-size': 11,
				'text-allow-overlap': false,
				'text-ignore-placement': false
			},
			paint: {
				'text-color': '#173e3b',
				'text-halo-color': '#fffdf7',
				'text-opacity': ['step', ['zoom'], 0, 11, 1],
				'text-halo-width': ['step', ['zoom'], 0, 11, 1.5]
			}
		});

		map.on('click', 'metro-barangay-fill', onClick);
		map.on('click', onMapClick);
		map.on('mouseenter', 'metro-barangay-fill', onMouseEnter);
		map.on('mouseleave', 'metro-barangay-fill', onMouseLeave);
	};

	return {
		addLayers,
		syncSelection,
		dispose: () => {
			map.off('click', 'metro-barangay-fill', onClick);
			map.off('click', onMapClick);
			map.off('mouseenter', 'metro-barangay-fill', onMouseEnter);
			map.off('mouseleave', 'metro-barangay-fill', onMouseLeave);
		}
	};
}
