import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson';

import cityData from './metro-cities.json';

export type MetroCityProperties = {
	id: string;
	name: string;
};

type SourceCityProperties = {
	adm3_name: string;
	adm3_pcode: string;
};

const sourceCities = cityData as FeatureCollection<Polygon, SourceCityProperties>;

export const metroCityBoundary: FeatureCollection<Polygon, MetroCityProperties> = {
	type: 'FeatureCollection',
	features: sourceCities.features.map((feature) => ({
		...feature,
		id: feature.properties.adm3_pcode,
		properties: {
			id: feature.properties.adm3_pcode,
			name: feature.properties.adm3_name
		}
	}))
};

export const metroCityGeometry: MultiPolygon = {
	type: 'MultiPolygon',
	coordinates: metroCityBoundary.features.map((feature) => feature.geometry.coordinates)
};

function boundsForCoordinates(coordinates: unknown) {
	let west = Infinity;
	let south = Infinity;
	let east = -Infinity;
	let north = -Infinity;

	function visit(value: unknown): void {
		if (!Array.isArray(value)) return;
		if (typeof value[0] === 'number' && typeof value[1] === 'number') {
			west = Math.min(west, value[0]);
			south = Math.min(south, value[1]);
			east = Math.max(east, value[0]);
			north = Math.max(north, value[1]);
			return;
		}
		for (const child of value) visit(child);
	}

	visit(coordinates);
	return [west, south, east, north] as const;
}

export const metroCityBounds = boundsForCoordinates(metroCityGeometry.coordinates);

const worldRing = [
	[-180, -85],
	[180, -85],
	[180, 85],
	[-180, 85],
	[-180, -85]
] as [number, number][];

const cityHoles = metroCityGeometry.coordinates.map(([outerRing]) => [...outerRing].reverse());

export const metroCityMask: Feature<Polygon> = {
	type: 'Feature',
	properties: null,
	geometry: {
		type: 'Polygon',
		coordinates: [worldRing, ...cityHoles]
	}
};

export const metroCityAttribution =
	'OCHA Philippines COD-AB, sourced from NAMRIA and PSA. CC BY-IGO.';
