import { describe, expect, it } from 'vitest';

import rawBarangays from './metro-barangays.json';
import { createMetroBarangays, searchMetroBarangays } from './barangays';

const barangays = createMetroBarangays(rawBarangays as Parameters<typeof createMetroBarangays>[0]);

describe('Metro Manila barangays', () => {
	it('contains the OCHA barangays for the three cities', () => {
		expect(barangays.features).toHaveLength(945);
		expect(new Set(barangays.features.map((feature) => feature.properties.cityName))).toEqual(
			new Set(['City of Manila', 'City of Marikina', 'City of Pasig'])
		);
	});

	it('searches barangay names without case sensitivity', () => {
		expect(searchMetroBarangays(barangays, 'san roque').length).toBeGreaterThan(0);
	});
});
