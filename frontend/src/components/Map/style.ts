import type { StyleSpecification } from 'maplibre-gl';

export function createMapStyle(): StyleSpecification {
  const key = import.meta.env.VITE_MAPTILER_KEY || '';

  return {
    version: 8,
    sources: {
      openmaptiles: {
        type: 'vector',
        url: `https://api.maptiler.com/tiles/v3/tiles.json?key=${key}`,
      },
    },
    glyphs: `https://api.maptiler.com/fonts/{fontstack}/{range}.pbf?key=${key}`,
    layers: [
      // Background — acts as water color since most of the world is ocean
      {
        id: 'background',
        type: 'background',
        paint: {
          'background-color': '#F8FAFC',
        },
      },
      // Land polygon fill
      {
        id: 'landcover',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landcover',
        paint: {
          'fill-color': '#E2E8F0',
          'fill-opacity': 0.6,
        },
      },
      // Land base (from landuse layer with no filter — catches all land)
      {
        id: 'land',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landuse',
        paint: {
          'fill-color': '#E2E8F0',
        },
      },
      // Industrial / commercial / port areas
      {
        id: 'landuse-industrial',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landuse',
        filter: [
          'in',
          'class',
          'industrial',
          'commercial',
          'port',
          'harbour',
        ],
        paint: {
          'fill-color': '#D1D5DB',
          'fill-opacity': 0.7,
        },
      },
      // Water fill — matches background so ocean/lakes are seamless
      {
        id: 'water',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'water',
        paint: {
          'fill-color': '#F8FAFC',
        },
      },
      // Shoreline / coastline stroke
      {
        id: 'shoreline',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'water',
        paint: {
          'line-color': '#94A3B8',
          'line-width': 1,
        },
      },
      // Country borders
      {
        id: 'boundary-country',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'boundary',
        filter: ['==', 'admin_level', 2],
        paint: {
          'line-color': '#CBD5E1',
          'line-width': 1,
        },
      },
      // Roads — very subtle, only major ones
      {
        id: 'road-major',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'transportation',
        filter: ['in', 'class', 'motorway', 'trunk', 'primary'],
        paint: {
          'line-color': '#CBD5E1',
          'line-width': 0.5,
          'line-opacity': 0.4,
        },
        minzoom: 6,
      },
      // Place labels — cities and towns
      {
        id: 'place-labels',
        type: 'symbol',
        source: 'openmaptiles',
        'source-layer': 'place',
        filter: ['in', 'class', 'city', 'town'],
        layout: {
          'text-field': '{name:latin}',
          'text-font': ['Open Sans Regular'],
          'text-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            3, 10,
            8, 14,
          ],
          'text-max-width': 8,
        },
        paint: {
          'text-color': '#475569',
          'text-halo-color': '#F8FAFC',
          'text-halo-width': 1.5,
        },
      },
      // Country labels
      {
        id: 'country-labels',
        type: 'symbol',
        source: 'openmaptiles',
        'source-layer': 'place',
        filter: ['==', 'class', 'country'],
        layout: {
          'text-field': '{name:latin}',
          'text-font': ['Open Sans Regular'],
          'text-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            2, 10,
            5, 14,
          ],
          'text-max-width': 8,
          'text-transform': 'uppercase',
          'text-letter-spacing': 0.1,
        },
        paint: {
          'text-color': '#94A3B8',
          'text-halo-color': '#F8FAFC',
          'text-halo-width': 1.5,
        },
        minzoom: 2,
        maxzoom: 7,
      },
    ],
  };
}
