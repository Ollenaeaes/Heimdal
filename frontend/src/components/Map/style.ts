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
      // Background — dark navy ocean
      {
        id: 'background',
        type: 'background',
        paint: {
          'background-color': '#0A1628',
        },
      },
      // Land polygon fill — dark charcoal
      {
        id: 'landcover',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landcover',
        paint: {
          'fill-color': '#1A2332',
          'fill-opacity': 0.6,
        },
      },
      // Land base
      {
        id: 'land',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'landuse',
        paint: {
          'fill-color': '#1A2332',
        },
      },
      // Industrial / commercial / port areas — slightly lighter
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
          'fill-color': '#243044',
          'fill-opacity': 0.7,
        },
      },
      // Water fill — matches dark ocean background
      {
        id: 'water',
        type: 'fill',
        source: 'openmaptiles',
        'source-layer': 'water',
        paint: {
          'fill-color': '#0A1628',
        },
      },
      // Shoreline / coastline stroke — subtle
      {
        id: 'shoreline',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'water',
        paint: {
          'line-color': '#2D4A6F',
          'line-width': 1,
        },
      },
      // Country borders — dim blue-gray
      {
        id: 'boundary-country',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'boundary',
        filter: ['==', 'admin_level', 2],
        paint: {
          'line-color': '#2D4A6F',
          'line-width': 0.8,
          'line-opacity': 0.6,
        },
      },
      // Roads — very subtle on dark base
      {
        id: 'road-major',
        type: 'line',
        source: 'openmaptiles',
        'source-layer': 'transportation',
        filter: ['in', 'class', 'motorway', 'trunk', 'primary'],
        paint: {
          'line-color': '#2D4A6F',
          'line-width': 0.5,
          'line-opacity': 0.3,
        },
        minzoom: 6,
      },
      // Place labels — light text on dark bg
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
          'text-color': '#8899AA',
          'text-halo-color': '#0A1628',
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
          'text-color': '#4A6580',
          'text-halo-color': '#0A1628',
          'text-halo-width': 1.5,
        },
        minzoom: 2,
        maxzoom: 7,
      },
    ],
  };
}
