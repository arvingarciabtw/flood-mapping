import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { homedir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import geojsonvt from 'geojson-vt';
import polygonClipping from 'polygon-clipping';
import vtpbf from 'vt-pbf';

const { intersection } = polygonClipping;
const run = promisify(execFile);
const projectRoot = process.cwd();
const sourceRoot = process.env.NOAH_DATA_DIR ?? path.join(homedir(), 'downloads/noah');
const sourceFile = path.join(sourceRoot, 'flood/5yr/metro-manila/MetroManila_Flood_5year.shp');
const outputRoot = path.join(projectRoot, 'static');
const dataRoot = path.join(projectRoot, 'src/lib/data');
const boundaryFile = path.join(dataRoot, 'metro-cities.json');
const barangayFile = path.join(dataRoot, 'metro-barangays.json');
const mapshaperBin = path.join(projectRoot, 'node_modules/mapshaper/bin/mapshaper');
const minZoom = 10;
const maxZoom = 15;

const cities = JSON.parse(await readFile(boundaryFile, 'utf8'));
const barangays = JSON.parse(await readFile(barangayFile, 'utf8'));
const cityBounds = bbox(cities);

function asMultiPolygon(geometry) {
	if (geometry.type === 'Polygon') return [geometry.coordinates];
	if (geometry.type === 'MultiPolygon') return geometry.coordinates;
	throw new Error(`Unsupported geometry type: ${geometry.type}`);
}

function bbox(value) {
	let minX = Infinity;
	let minY = Infinity;
	let maxX = -Infinity;
	let maxY = -Infinity;

	function visit(coordinates) {
		if (typeof coordinates[0] === 'number') {
			minX = Math.min(minX, coordinates[0]);
			minY = Math.min(minY, coordinates[1]);
			maxX = Math.max(maxX, coordinates[0]);
			maxY = Math.max(maxY, coordinates[1]);
			return;
		}
		for (const child of coordinates) visit(child);
	}

	for (const feature of value.features ?? [value]) visit(feature.geometry.coordinates);
	return [minX, minY, maxX, maxY];
}

function bboxesOverlap(left, right) {
	return left[0] <= right[2] && left[2] >= right[0] && left[1] <= right[3] && left[3] >= right[1];
}

function ringArea(ring) {
	let area = 0;
	for (let index = 0; index < ring.length - 1; index += 1) {
		area += ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1];
	}
	return Math.abs(area) / 2;
}

function multiPolygonArea(multiPolygon) {
	return multiPolygon.reduce(
		(total, polygon) =>
			total +
			ringArea(polygon[0]) -
			polygon.slice(1).reduce((sum, hole) => sum + ringArea(hole), 0),
		0
	);
}

function floodClass(value) {
	const parsed = Number(value);
	if (![1, 2, 3].includes(parsed)) throw new Error(`Unsupported flood class: ${value}`);
	return parsed;
}

function summaryForClasses(classes) {
	const orderedClasses = [1, 2, 3].filter((value) => classes.has(value));
	return {
		classes: orderedClasses.map((value) => ['Mild', 'Moderate', 'Severe'][value - 1]),
		summary:
			orderedClasses.length === 0
				? 'NoData'
				: orderedClasses.length === 1
					? ['Mild', 'Moderate', 'Severe'][orderedClasses[0] - 1]
					: 'Mixed'
	};
}

async function loadFloodData(tempRoot) {
	const clippedFile = path.join(tempRoot, 'flood-5yr-cells.json');
	const summaryFile = path.join(tempRoot, 'flood-5yr-summary.json');
	const sourceArgs = [mapshaperBin, sourceFile, '-clip', boundaryFile];

	await run(process.execPath, [
		...sourceArgs,
		'-o',
		clippedFile,
		'format=geojson',
		'precision=0.000001'
	]);
	await run(process.execPath, [
		...sourceArgs,
		'-clean',
		'-dissolve',
		'Var',
		'-simplify',
		'10%',
		'-o',
		summaryFile,
		'format=geojson',
		'precision=0.000001'
	]);

	const cellSource = JSON.parse(await readFile(clippedFile, 'utf8'));
	const summarySource = JSON.parse(await readFile(summaryFile, 'utf8'));
	const cellCollection = {
		type: 'FeatureCollection',
		features: cellSource.features
			.filter((feature) => feature.geometry)
			.map((feature) => ({
				type: 'Feature',
				properties: { Var: floodClass(feature.properties?.Var) },
				geometry: feature.geometry
			}))
	};
	const summaryFeatures = summarySource.features
		.filter((feature) => feature.geometry)
		.map((feature) => ({
			...feature,
			properties: { Var: floodClass(feature.properties?.Var) },
			bbox: bbox(feature)
		}));

	console.log(
		`Flood 5-year: ${cellCollection.features.length} cell features, ${summaryFeatures.length} summary features`
	);
	return { cellCollection, summaryFeatures };
}

function longitudeToTileX(longitude, zoom) {
	return Math.floor(((longitude + 180) / 360) * 2 ** zoom);
}

function latitudeToTileY(latitude, zoom) {
	const radians = (latitude * Math.PI) / 180;
	return Math.floor(
		((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) * 2 ** zoom
	);
}

async function writeVectorTiles(collection) {
	const outputDirectory = path.join(outputRoot, 'metro-manila-flood-5yr-tiles');
	await rm(outputDirectory, { recursive: true, force: true });

	const tileIndex = geojsonvt(collection, {
		buffer: 0,
		extent: 4096,
		indexMaxPoints: 0,
		indexMaxZoom: maxZoom,
		maxZoom,
		tolerance: 0
	});

	for (let zoom = minZoom; zoom <= maxZoom; zoom += 1) {
		const tileCount = 2 ** zoom;
		const minX = Math.max(0, longitudeToTileX(cityBounds[0], zoom) - 1);
		const maxX = Math.min(tileCount - 1, longitudeToTileX(cityBounds[2], zoom) + 1);
		const minY = Math.max(0, latitudeToTileY(cityBounds[3], zoom) - 1);
		const maxY = Math.min(tileCount - 1, latitudeToTileY(cityBounds[1], zoom) + 1);

		for (let x = minX; x <= maxX; x += 1) {
			for (let y = minY; y <= maxY; y += 1) {
				const tile = tileIndex.getTile(zoom, x, y) ?? { features: [] };
				const tilePath = path.join(outputDirectory, String(zoom), String(x), `${y}.pbf`);
				await mkdir(path.dirname(tilePath), { recursive: true });
				await writeFile(
					tilePath,
					vtpbf.fromGeojsonVt({ flood: tile }, { version: 2, extent: 4096 })
				);
			}
		}
	}
}

function buildSummaries(summaryFeatures) {
	const areas = [
		...cities.features.map((feature) => ({
			id: feature.properties.adm3_pcode,
			geometry: feature.geometry
		})),
		...barangays.features.map((feature) => ({
			id: feature.properties.adm4_pcode,
			geometry: feature.geometry
		}))
	];
	const summaries = {};

	for (const area of areas) {
		const areaCoordinates = asMultiPolygon(area.geometry);
		const areaBbox = bbox(area);
		const classes = new Set();

		for (const feature of summaryFeatures) {
			if (!bboxesOverlap(areaBbox, feature.bbox)) continue;
			const overlap = intersection(feature.geometry.coordinates, areaCoordinates);
			if (overlap.length > 0 && multiPolygonArea(overlap) > 1e-12) {
				classes.add(feature.properties.Var);
			}
		}

		summaries[area.id] = summaryForClasses(classes);
	}

	return summaries;
}

const tempRoot = path.join(projectRoot, '.svelte-kit/flood-data');
await mkdir(tempRoot, { recursive: true });
const { cellCollection, summaryFeatures } = await loadFloodData(tempRoot);
await writeVectorTiles(cellCollection);
await writeFile(
	path.join(dataRoot, 'metro-manila-flood-summaries.json'),
	`${JSON.stringify(buildSummaries(summaryFeatures), null, 2)}\n`
);
await writeFile(
	path.join(dataRoot, 'flood-data-manifest.json'),
	`${JSON.stringify(
		{
			generatedAt: new Date().toISOString(),
			coverage: ['City of Manila', 'City of Marikina', 'City of Pasig'],
			returnPeriod: '5-year',
			sourceField: 'Var',
			tilePath: '/metro-manila-flood-5yr-tiles/{z}/{x}/{y}.pbf'
		},
		null,
		2
	)}\n`
);

console.log('Wrote Metro Manila flood tiles and area summaries');
