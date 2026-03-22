import { useState, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useVesselStore } from '../hooks/useVesselStore';
import { getMapInstance } from './Map/mapInstance';
import { RISK_COLORS } from '../utils/riskColors';

interface EezCountry {
  iso: string;
  name: string;
}

interface PortCall {
  port_name: string;
  lat: number;
  lon: number;
  start_time: string | null;
  end_time: string | null;
}

interface ReportVessel {
  mmsi: number;
  imo: number | null;
  name: string | null;
  ship_type: string | null;
  flag: string | null;
  risk_tier: string;
  risk_score: number | null;
  sanctions_programs: string[];
  sanctions_match_count: number;
  last_lat: number | null;
  last_lon: number | null;
  last_position_time: string | null;
  length: number | null;
  width: number | null;
  owner: string | null;
  operator: string | null;
  port_calls: PortCall[];
  presence: {
    entered_at: string | null;
    exited_at: string | null;
    total_hours: number;
    was_inside_at_start: boolean;
    still_inside: boolean;
  };
}

interface EezReportData {
  zone: { iso_sov: string; name: string; sovereign: string };
  time_range: { start: string; end: string };
  total_sanctioned_vessels: number;
  vessels: ReportVessel[];
}

const TIME_PRESETS = [
  { label: '5h', hours: 5 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: '30d', hours: 720 },
] as const;

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
    }) + ' UTC';
  } catch {
    return iso;
  }
}

function exportCsv(report: EezReportData) {
  const headers = [
    'MMSI', 'IMO', 'Name', 'Type', 'Flag', 'Risk Tier', 'Risk Score',
    'Sanctions Programs', 'Owner', 'Operator',
    'Entered EEZ', 'Exited EEZ', 'Total Hours Inside',
    'Was Inside At Start', 'Still Inside',
    'Port Calls', 'Last Position Time',
  ];
  const rows = report.vessels.map((v) => [
    v.mmsi,
    v.imo ?? '',
    v.name ?? '',
    v.ship_type ?? '',
    v.flag ?? '',
    v.risk_tier,
    v.risk_score ?? '',
    v.sanctions_programs.join('; '),
    v.owner ?? '',
    v.operator ?? '',
    v.presence?.entered_at ?? '',
    v.presence?.exited_at ?? '',
    v.presence?.total_hours ?? '',
    v.presence?.was_inside_at_start ? 'Yes' : 'No',
    v.presence?.still_inside ? 'Yes' : 'No',
    v.port_calls.map((pc) => `${pc.port_name} (${pc.start_time ?? '?'})`).join('; '),
    v.last_position_time ?? '',
  ]);

  const csvContent = [
    `# EEZ Sanctions Report: ${report.zone.sovereign}`,
    `# Period: ${report.time_range.start} to ${report.time_range.end}`,
    `# Total sanctioned vessels: ${report.total_sanctioned_vessels}`,
    '',
    headers.join(','),
    ...rows.map((r) =>
      r.map((cell) => {
        const s = String(cell);
        return s.includes(',') || s.includes('"') || s.includes('\n')
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      }).join(','),
    ),
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `eez-report-${report.zone.iso_sov}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function EezReportButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className={`w-full text-left px-3 py-1.5 text-xs rounded transition-colors ${
          open
            ? 'bg-blue-600/20 text-blue-400'
            : 'text-slate-300 hover:bg-[#1F2937] hover:text-white'
        }`}
        data-testid="eez-report-button"
      >
        EEZ Sanctions Report
      </button>
      {open && <EezReportPanel onClose={() => setOpen(false)} />}
    </>
  );
}

function EezReportPanel({ onClose }: { onClose: () => void }) {
  const [selectedIso, setSelectedIso] = useState('');
  const [hours, setHours] = useState(168); // default 7 days
  const [report, setReport] = useState<EezReportData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedMmsi, setExpandedMmsi] = useState<number | null>(null);
  const selectVessel = useVesselStore((s) => s.selectVessel);

  // Fetch country list
  const { data: countries } = useQuery<EezCountry[]>({
    queryKey: ['eez-countries'],
    queryFn: async () => {
      const res = await fetch('/api/maritime-zones/countries');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    staleTime: Infinity,
  });

  // Auto-select first country when loaded
  useEffect(() => {
    if (countries && countries.length > 0 && !selectedIso) {
      setSelectedIso(countries[0].iso);
    }
  }, [countries, selectedIso]);

  const handleSearch = useCallback(async () => {
    if (!selectedIso) return;
    setIsLoading(true);
    setError(null);
    setReport(null);

    try {
      const res = await fetch(
        `/api/maritime-zones/eez-report?iso_sov=${selectedIso}&hours=${hours}`,
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(body.detail ?? `Failed: ${res.status}`);
      }
      const data: EezReportData = await res.json();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setIsLoading(false);
    }
  }, [selectedIso, hours]);

  const handleFlyTo = useCallback(
    (lat: number, lon: number, mmsi: number) => {
      const map = getMapInstance();
      if (map) {
        map.flyTo({ center: [lon, lat], zoom: 8, duration: 1500 });
      }
      selectVessel(mmsi);
    },
    [selectVessel],
  );

  return (
    <div
      className="absolute top-12 left-3 z-50 w-96 rounded-lg shadow-xl border border-slate-700/50 overflow-hidden flex flex-col"
      style={{ backgroundColor: 'rgba(10, 14, 23, 0.95)', maxHeight: 'calc(100vh - 120px)' }}
      data-testid="eez-report-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/50 shrink-0">
        <h3 className="text-xs font-semibold text-slate-300">EEZ Sanctions Report</h3>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-red-400 transition-colors"
          aria-label="Close"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Controls */}
      <div className="p-3 space-y-3 border-b border-slate-700/50 shrink-0">
        {/* Country selector */}
        <div>
          <label className="text-[0.65rem] text-slate-500 block mb-1">Country EEZ</label>
          <select
            value={selectedIso}
            onChange={(e) => setSelectedIso(e.target.value)}
            className="w-full px-2 py-1.5 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-blue-500 focus:outline-none"
            data-testid="eez-country-select"
          >
            {!countries && <option value="">Loading...</option>}
            {countries?.map((c) => (
              <option key={c.iso} value={c.iso}>
                {c.name} ({c.iso})
              </option>
            ))}
          </select>
        </div>

        {/* Time range presets */}
        <div>
          <label className="text-[0.65rem] text-slate-500 block mb-1">Time Range</label>
          <div className="flex gap-1">
            {TIME_PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => setHours(p.hours)}
                className={`flex-1 py-1 text-xs rounded transition-colors ${
                  hours === p.hours
                    ? 'bg-blue-600 text-white'
                    : 'bg-[#1F2937] text-slate-400 hover:text-white hover:bg-slate-700 border border-[#374151]'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Search button */}
        <button
          onClick={handleSearch}
          disabled={isLoading || !selectedIso}
          className="w-full py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 disabled:cursor-wait text-white text-xs font-medium rounded transition-colors"
          data-testid="eez-report-search"
        >
          {isLoading ? 'Searching...' : 'Generate Report'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="px-3 py-2 shrink-0">
          <p className="text-xs text-red-400">{error}</p>
        </div>
      )}

      {/* Results */}
      {report && (
        <div className="flex-1 overflow-y-auto min-h-0">
          {/* Summary */}
          <div className="px-3 py-2 border-b border-slate-700/30">
            <div className="text-xs text-slate-400">
              <span className="text-slate-200 font-medium">{report.zone.sovereign}</span> EEZ
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-2xl font-bold text-white">
                {report.total_sanctioned_vessels}
              </span>
              <span className="text-xs text-slate-500">
                sanctioned vessel{report.total_sanctioned_vessels !== 1 ? 's' : ''}
              </span>
            </div>
            <div className="text-[0.6rem] text-slate-600 mt-0.5">
              {formatDateTime(report.time_range.start)} — {formatDateTime(report.time_range.end)}
            </div>
            {report.vessels.length > 0 && (
              <button
                onClick={() => exportCsv(report)}
                className="mt-2 px-2 py-1 text-[0.65rem] bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
              >
                Export CSV
              </button>
            )}
          </div>

          {/* Vessel list */}
          {report.vessels.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-slate-500">
              No sanctioned vessels found in this EEZ during the selected period.
            </div>
          ) : (
            <div className="divide-y divide-slate-800/50">
              {report.vessels.map((v) => (
                <div key={v.mmsi} className="px-3 py-2">
                  {/* Vessel header */}
                  <button
                    onClick={() => setExpandedMmsi(expandedMmsi === v.mmsi ? null : v.mmsi)}
                    className="w-full text-left"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: RISK_COLORS[v.risk_tier] ?? '#888' }}
                      />
                      <span className="text-xs text-slate-200 font-medium truncate">
                        {v.name ?? `MMSI ${v.mmsi}`}
                      </span>
                      <span className="text-[0.6rem] text-slate-500 ml-auto shrink-0">
                        {v.flag ?? '??'}
                      </span>
                      {v.port_calls.length > 0 && (
                        <span className="text-[0.55rem] px-1 py-0.5 rounded bg-cyan-900/40 text-cyan-400 shrink-0">
                          {v.port_calls.length} port call{v.port_calls.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[0.6rem] text-slate-500">
                        {v.ship_type ?? 'Unknown type'}
                      </span>
                      <span className="text-[0.6rem] text-slate-600">
                        IMO {v.imo ?? '—'} / MMSI {v.mmsi}
                      </span>
                    </div>
                    {v.presence && (
                      <div className="flex items-center gap-2 mt-0.5 text-[0.6rem]">
                        <span className="text-slate-400">
                          {v.presence.total_hours}h inside
                        </span>
                        {v.presence.still_inside && (
                          <span className="px-1 py-0.5 rounded bg-green-900/40 text-green-400 text-[0.55rem]">
                            Currently inside
                          </span>
                        )}
                      </div>
                    )}
                  </button>

                  {/* Expanded details */}
                  {expandedMmsi === v.mmsi && (
                    <div className="mt-2 ml-4 space-y-2">
                      {/* Sanctions info */}
                      <div>
                        <span className="text-[0.6rem] text-slate-500 block">Sanctions Programs</span>
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {v.sanctions_programs.map((p) => (
                            <span
                              key={p}
                              className="text-[0.55rem] px-1.5 py-0.5 rounded bg-red-900/30 text-red-400"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* EEZ Presence */}
                      {v.presence && (
                        <div className="text-[0.6rem] text-slate-400">
                          <span className="text-slate-500 block mb-0.5">EEZ Presence</span>
                          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                            <span>Entered:</span>
                            <span className="text-slate-300">
                              {v.presence.was_inside_at_start
                                ? 'Already inside at start'
                                : formatDateTime(v.presence.entered_at)}
                            </span>
                            <span>Exited:</span>
                            <span className="text-slate-300">
                              {v.presence.still_inside
                                ? 'Still inside'
                                : formatDateTime(v.presence.exited_at)}
                            </span>
                            <span>Total time:</span>
                            <span className="text-slate-300">{v.presence.total_hours}h</span>
                          </div>
                        </div>
                      )}

                      {/* Owner/operator */}
                      {(v.owner || v.operator) && (
                        <div className="text-[0.6rem] text-slate-400">
                          {v.owner && <div>Owner: <span className="text-slate-300">{v.owner}</span></div>}
                          {v.operator && <div>Operator: <span className="text-slate-300">{v.operator}</span></div>}
                        </div>
                      )}

                      {/* Port calls */}
                      {v.port_calls.length > 0 && (
                        <div>
                          <span className="text-[0.6rem] text-slate-500 block mb-1">Port Calls</span>
                          {v.port_calls.map((pc, i) => (
                            <div
                              key={i}
                              className="flex items-center gap-2 text-[0.6rem] py-0.5 text-slate-400"
                            >
                              <span className="w-1 h-1 rounded-full bg-cyan-500 shrink-0" />
                              <span className="text-slate-300">{pc.port_name ?? 'Unknown port'}</span>
                              <span className="text-slate-600 ml-auto">
                                {formatDateTime(pc.start_time)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex gap-2 pt-1">
                        {v.last_lat != null && v.last_lon != null && (
                          <button
                            onClick={() => handleFlyTo(v.last_lat!, v.last_lon!, v.mmsi)}
                            className="text-[0.6rem] text-blue-400 hover:text-blue-300"
                          >
                            Fly to vessel
                          </button>
                        )}
                        <span className="text-[0.6rem] text-slate-600">
                          Last seen: {formatDateTime(v.last_position_time)}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
