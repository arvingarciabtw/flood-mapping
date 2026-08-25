import { describe, expect, it } from 'vitest';

import { metroCityBoundary, metroCityBounds, metroCityMask } from './metro-boundary';

describe('Metro Manila boundaries', () => {
	it('contains the three requested cities', () => {
		expect(metroCityBoundary.features.map((feature) => feature.properties.name)).toEqual([
			'City of Manila',
			'City of Marikina',
			'City of Pasig'
		]);
	});

	it('has a valid combined map extent and mask', () => {
		expect(metroCityBounds).toEqual([
			expect.any(Number),
			expect.any(Number),
			expect.any(Number),
			expect.any(Number)
		]);
		expect(metroCityMask.geometry.coordinates).toHaveLength(4);
	});
});
