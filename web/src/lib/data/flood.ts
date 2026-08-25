export type FloodHazardClass = 'Mild' | 'Moderate' | 'Severe';

export type FloodHazardSummary = {
	classes: FloodHazardClass[];
	summary: FloodHazardClass | 'Mixed' | 'NoData';
};

export const floodHazardColors: Record<FloodHazardClass, string> = {
	Mild: '#f2c94c',
	Moderate: '#f2994a',
	Severe: '#eb5757'
};

export const floodHazard = {
	key: '5yr',
	shortName: '5-year return period',
	tilePath: '/metro-manila-flood-5yr-tiles/{z}/{x}/{y}.pbf',
	colors: floodHazardColors
} as const;

export const floodHazardMetadata = {
	source: 'UP NOAH Center',
	sourceUrl: 'https://noah.up.edu.ph/',
	coverage: 'Manila, Pasig, and Marikina cities.',
	returnPeriod: '5-year',
	classification: 'Source values 1, 2, and 3 are shown as Mild, Moderate, and Severe.',
	caveat: 'This is modeled flood hazard information, not a live warning.'
} as const;

export function floodClassForValue(value: unknown): FloodHazardClass {
	if (value === 1 || value === '1') return 'Mild';
	if (value === 2 || value === '2') return 'Moderate';
	if (value === 3 || value === '3') return 'Severe';
	throw new Error(`Unsupported flood class: ${String(value)}`);
}

export function floodSummaryForClasses(classes: Iterable<FloodHazardClass>): FloodHazardSummary {
	const classSet = new Set(classes);
	const orderedClasses = (['Mild', 'Moderate', 'Severe'] as const).filter((value) =>
		classSet.has(value)
	);

	return {
		classes: orderedClasses,
		summary:
			orderedClasses.length === 0
				? 'NoData'
				: orderedClasses.length === 1
					? orderedClasses[0]
					: 'Mixed'
	};
}
