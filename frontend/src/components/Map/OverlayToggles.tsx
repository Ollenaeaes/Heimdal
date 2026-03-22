import { useState } from 'react';
import { useVesselStore } from '../../hooks/useVesselStore';
import type { GfwEventType } from '../../types/api';
import { GFW_EVENT_COLORS } from '../../utils/eventIcons';

export interface OverlayToggleState {
  showStsZones: boolean;
  showTerminals: boolean;
  showEez: boolean;
  showSeaBorders: boolean;
  showSeaBordersEez: boolean;
  showSeaBorders12nm: boolean;
  showSarDetections: boolean;
  showGfwEvents: boolean;
  showInfrastructure: boolean;
  showGnssZones: boolean;
  showNetwork: boolean;
}

export interface OverlayTogglesProps {
  state: OverlayToggleState;
  onChange: (newState: OverlayToggleState) => void;
  /** When true, renders without its own container (for embedding in a dropdown). */
  inline?: boolean;
}

const ALL_GFW_EVENT_TYPES: GfwEventType[] = ['ENCOUNTER', 'LOITERING', 'AIS_DISABLING', 'PORT_VISIT'];
const GFW_EVENT_LABELS: Record<GfwEventType, string> = {
  ENCOUNTER: 'Encounters',
  LOITERING: 'Loitering',
  AIS_DISABLING: 'AIS Disabling',
  PORT_VISIT: 'Port Visits',
};

export function OverlayToggles({ state, onChange, inline }: OverlayTogglesProps) {
  const [expanded, setExpanded] = useState(false);
  const darkShipsOnly = useVesselStore((s) => s.filters.darkShipsOnly);
  const showGfwEventTypes = useVesselStore((s) => s.filters.showGfwEventTypes);
  const setFilter = useVesselStore((s) => s.setFilter);

  const toggle = (key: keyof OverlayToggleState) => {
    onChange({ ...state, [key]: !state[key] });
  };

  const toggleDarkShips = () => {
    setFilter({ darkShipsOnly: !darkShipsOnly });
  };

  const toggleGfwEventType = (eventType: GfwEventType) => {
    const current = new Set(showGfwEventTypes);
    if (current.has(eventType)) {
      current.delete(eventType);
    } else {
      current.add(eventType);
    }
    setFilter({ showGfwEventTypes: Array.from(current) });
  };

  // Count active overlays
  const activeCount = [
    state.showStsZones, state.showTerminals, state.showSeaBorders,
    state.showSarDetections, state.showGfwEvents, state.showInfrastructure,
    state.showGnssZones, state.showNetwork,
  ].filter(Boolean).length;

  // Standalone mode: collapsed/expanded toggle
  if (!inline) {
    if (!expanded) {
      return (
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-[#0A0E17]/80 border border-[#1F2937] backdrop-blur-md text-slate-300 hover:text-white hover:bg-[#111827]/90 transition-colors text-xs"
          title="Toggle map layers"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="1" y="1" width="6" height="6" rx="1" opacity="0.6" />
            <rect x="9" y="1" width="6" height="6" rx="1" opacity="0.4" />
            <rect x="1" y="9" width="6" height="6" rx="1" opacity="0.4" />
            <rect x="9" y="9" width="6" height="6" rx="1" opacity="0.2" />
          </svg>
          Layers
          {activeCount > 0 && (
            <span className="px-1 py-0.5 rounded text-[0.6rem] font-mono bg-blue-500/20 text-blue-400">
              {activeCount}
            </span>
          )}
        </button>
      );
    }

    return (
      <div className="flex flex-col gap-2 bg-[#0A0E17]/80 p-3 rounded border border-[#1F2937] backdrop-blur-md text-white text-xs">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[0.7rem] font-medium text-slate-400 uppercase tracking-wider">Layers</span>
          <button
            onClick={() => setExpanded(false)}
            className="text-slate-500 hover:text-slate-300 text-sm leading-none px-1"
            title="Collapse"
          >
            ✕
          </button>
        </div>
        <LayerCheckboxes state={state} onChange={onChange} toggle={toggle}
          darkShipsOnly={darkShipsOnly} toggleDarkShips={toggleDarkShips}
          showGfwEventTypes={showGfwEventTypes} toggleGfwEventType={toggleGfwEventType} />
      </div>
    );
  }

  // Inline mode: just the checkboxes, no wrapper
  return (
    <div className="p-2 flex flex-col gap-2 text-white text-xs">
      <LayerCheckboxes state={state} onChange={onChange} toggle={toggle}
        darkShipsOnly={darkShipsOnly} toggleDarkShips={toggleDarkShips}
        showGfwEventTypes={showGfwEventTypes} toggleGfwEventType={toggleGfwEventType} />
    </div>
  );
}

/** Shared checkbox list used by both inline and standalone modes. */
function LayerCheckboxes({
  state, toggle, darkShipsOnly, toggleDarkShips, showGfwEventTypes, toggleGfwEventType,
}: {
  state: OverlayToggleState;
  onChange: (s: OverlayToggleState) => void;
  toggle: (key: keyof OverlayToggleState) => void;
  darkShipsOnly: boolean;
  toggleDarkShips: () => void;
  showGfwEventTypes: GfwEventType[];
  toggleGfwEventType: (t: GfwEventType) => void;
}) {
  return (
    <>
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showStsZones}
          onChange={() => toggle('showStsZones')}
          className="accent-amber-500"
        />
        STS Zones
      </label>
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showTerminals}
          onChange={() => toggle('showTerminals')}
          className="accent-red-500"
        />
        Russian Terminals
      </label>
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showSeaBorders}
          onChange={() => toggle('showSeaBorders')}
          className="accent-blue-500"
        />
        Sea Borders
      </label>
      {state.showSeaBorders && (
        <div className="ml-4 flex flex-col gap-1.5">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={state.showSeaBordersEez}
              onChange={() => toggle('showSeaBordersEez')}
              className="accent-blue-400"
            />
            <span className="text-blue-300">EEZ (200nm)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={state.showSeaBorders12nm}
              onChange={() => toggle('showSeaBorders12nm')}
              className="accent-blue-300"
            />
            <span className="text-blue-200">Territorial Sea (12nm)</span>
          </label>
        </div>
      )}
      <div className="border-t border-[#1F2937] my-1" />
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showSarDetections}
          onChange={() => toggle('showSarDetections')}
          className="accent-white"
        />
        SAR Detections
      </label>
      {state.showSarDetections && (
        <label className="flex items-center gap-2 cursor-pointer ml-4" data-testid="dark-ships-toggle">
          <input
            type="checkbox"
            checked={darkShipsOnly}
            onChange={toggleDarkShips}
            className="accent-red-500"
          />
          <span className="text-red-300">Dark Ships Only</span>
        </label>
      )}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showGfwEvents}
          onChange={() => toggle('showGfwEvents')}
          className="accent-orange-500"
        />
        GFW Events
      </label>
      {state.showGfwEvents && (
        <div className="ml-4 flex flex-col gap-1.5">
          {ALL_GFW_EVENT_TYPES.map((eventType) => (
            <label key={eventType} className="flex items-center gap-2 cursor-pointer" data-testid={`gfw-type-${eventType}`}>
              <input
                type="checkbox"
                checked={showGfwEventTypes.includes(eventType)}
                onChange={() => toggleGfwEventType(eventType)}
                style={{ accentColor: GFW_EVENT_COLORS[eventType] }}
              />
              <span className="text-gray-300">{GFW_EVENT_LABELS[eventType]}</span>
            </label>
          ))}
        </div>
      )}
      <div className="border-t border-[#1F2937] my-1" />
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showInfrastructure}
          onChange={() => toggle('showInfrastructure')}
          className="accent-cyan-500"
        />
        Infrastructure
      </label>
      {state.showInfrastructure && (
        <div className="ml-4 flex flex-col gap-1 text-[0.65rem] text-slate-400">
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 inline-block" style={{ backgroundColor: '#3B82F6' }} />
            Telecom Cable
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 inline-block" style={{ backgroundColor: '#EAB308' }} />
            Power Cable
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 inline-block" style={{ backgroundColor: '#F97316' }} />
            Pipeline (Gas/Oil)
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 inline-block" style={{ backgroundColor: '#EF4444' }} />
            Alert (slow transit / alignment)
          </div>
        </div>
      )}
      <label className="flex items-center gap-2 cursor-pointer" data-testid="gnss-zones-toggle">
        <input
          type="checkbox"
          checked={state.showGnssZones}
          onChange={() => toggle('showGnssZones')}
          className="accent-red-500"
        />
        GNSS / Spoofing
      </label>
      <label className="flex items-center gap-2 cursor-pointer" data-testid="network-toggle">
        <input
          type="checkbox"
          checked={state.showNetwork}
          onChange={() => toggle('showNetwork')}
          className="accent-purple-500"
        />
        Network
      </label>
    </>
  );
}
