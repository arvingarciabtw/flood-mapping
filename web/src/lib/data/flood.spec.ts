import { describe, expect, it } from 'vitest';

import { floodClassForValue, floodHazardColors, floodSummaryForClasses } from './flood';

describe('flood data', () => {
	it('maps source values to the displayed classes', () => {
		expect([1, 2, 3].map(floodClassForValue)).toEqual(['Mild', 'Moderate', 'Severe']);
	});

	it('uses the warm flood palette', () => {
		expect(floodHazardColors).toEqual({
			Mild: '#f2c94c',
			Moderate: '#f2994a',
			Severe: '#eb5757'
		});
	});

	it('summarizes intersecting classes in source order', () => {
		expect(floodSummaryForClasses(['Severe', 'Mild'])).toEqual({
			classes: ['Mild', 'Severe'],
			summary: 'Mixed'
		});
	});
});
