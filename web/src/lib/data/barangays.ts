import type { FeatureCollection, MultiPolygon, Point, Polygon } from 'geojson';

import type { FloodHazardSummary } from './flood';
import barangayDataUrl from './metro-barangays.json?url';
import barangayLabelPointData from './metro-barangay-label-points.json';
import floodSummaryData from './metro-manila-flood-summaries.json';

export type BarangayProperties = {
	id: string;
	name: string;
	cityId: string;
	cityName: string;
	floodHazard: FloodHazardSummary;
};

export type BarangayCollection = FeatureCollection<Polygon | MultiPolygon, BarangayProperties>;

type SourceBarangayProperties = {
	adm4_name: string;
	adm4_pcode: string;
	adm3_name: string;
	adm3_pcode: string;
};

type FloodSummaryData = Record<string, FloodHazardSummary>;
const floodSummaries = floodSummaryData as FloodSummaryData;

export function createMetroBarangays(
	rawBarangays: FeatureCollection<Polygon | MultiPolygon, SourceBarangayProperties>
): BarangayCollection {
	return {
		type: 'FeatureCollection',
		features: rawBarangays.features.map((feature) => ({
			...feature,
			id: feature.properties.adm4_pcode,
			properties: {
				id: feature.properties.adm4_pcode,
				name: feature.properties.adm4_name,
				cityId: feature.properties.adm3_pcode,
				cityName: feature.properties.adm3_name,
				floodHazard: floodSummaries[feature.properties.adm4_pcode] ?? {
					classes: [],
					summary: 'NoData'
				}
			}
		}))
	};
}

let barangaysPromise: Promise<BarangayCollection> | null = null;

export function loadMetroBarangays(): Promise<BarangayCollection> {
	if (!barangaysPromise) {
		barangaysPromise = fetch(barangayDataUrl)
			.then(async (response) => {
				if (!response.ok) throw new Error(`Barangay data returned ${response.status}`);
				return createMetroBarangays(
					(await response.json()) as FeatureCollection<
						Polygon | MultiPolygon,
						SourceBarangayProperties
					>
				);
			})
			.catch((error) => {
				barangaysPromise = null;
				throw error;
			});
	}
	return barangaysPromise;
}

export const metroBarangayLabelPoints = barangayLabelPointData as FeatureCollection<
	Point,
	Pick<BarangayProperties, 'id' | 'name'>
>;

function normalizeSearch(value: string): string {
	return value
		.normalize('NFKD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLocaleLowerCase('en-PH')
		.trim();
}

export function searchMetroBarangays(
	barangays: BarangayCollection,
	query: string
): BarangayProperties[] {
	const normalizedQuery = normalizeSearch(query);
	if (!normalizedQuery) return [];

	return barangays.features
		.filter((feature) => normalizeSearch(feature.properties.name).includes(normalizedQuery))
		.map((feature) => feature.properties);
}

export const metroBarangayAttribution =
	'OCHA Philippines COD-AB, sourced from NAMRIA and PSA. CC BY-IGO.';
