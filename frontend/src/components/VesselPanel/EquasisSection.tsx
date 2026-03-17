import { useState } from 'react';
import type { EquasisData } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

export const FOC_FLAGS = new Set([
  'Panama',
  'Liberia',
  'Marshall Islands',
  'Bahamas',
  'Antigua and Barbuda',
  'Comoros',
  'Palau',
  'Cameroon',
  'Togo',
  'Malta',
  'Cyprus',
  'Bermuda',
  'Vanuatu',
  'Moldova',
  'Mongolia',
  'Bolivia',
  'Honduras',
  'Belize',
  'Saint Kitts and Nevis',
  'Sierra Leone',
  'Tanzania',
  'Barbados',
  'Cook Islands',
]);

interface EquasisSectionProps {
  mmsi: number;
  equasis: EquasisData | null | undefined;
}

export function formatUploadDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function getDeficiencyColor(count: number): string {
  if (count === 0) return 'text-green-400';
  if (count <= 5) return 'text-yellow-400';
  return 'text-red-400';
}

export function isFlagOfConvenience(flag: string): boolean {
  return FOC_FLAGS.has(flag);
}

function CollapsibleSubsection({
  title,
  testId,
  children,
}: {
  title: string;
  testId: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#1F2937] last:border-b-0" data-testid={testId}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full text-left py-2 px-1"
        data-testid={`${testId}-toggle`}
      >
        <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
          {title}
        </span>
        <span className="text-gray-500 text-xs">{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && <div className="pb-3 px-1">{children}</div>}
    </div>
  );
}

function ShipParticulars({ data }: { data: Record<string, any> }) {
  const fields = [
    ['IMO', data.imo],
    ['MMSI', data.mmsi],
    ['Name', data.name],
    ['Gross Tonnage', data.gross_tonnage],
    ['DWT', data.dwt],
    ['Type', data.type_of_ship],
    ['Build Year', data.year_of_build],
    ['Flag', data.flag],
    ['Status', data.status],
  ];
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
      {fields.map(([label, value]) => (
        <div key={label as string}>
          <dt className="text-gray-500 text-xs">{label as string}</dt>
          <dd className="text-gray-300">{value ?? '\u2014'}</dd>
        </div>
      ))}
    </div>
  );
}

function ManagementTable({ entries }: { entries: any[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-[#1F2937]">
            <th className="text-left py-1 pr-2">Role</th>
            <th className="text-left py-1 pr-2">Company</th>
            <th className="text-left py-1 pr-2">Address</th>
            <th className="text-left py-1">Date of Effect</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry: any, i: number) => {
            const isCurrent = !entry.date_to;
            return (
              <tr
                key={i}
                className={`border-b border-[#1F2937] ${isCurrent ? 'text-blue-300 font-medium' : 'text-gray-400'}`}
              >
                <td className="py-1 pr-2">{entry.role ?? '\u2014'}</td>
                <td className="py-1 pr-2">{entry.company_name ?? entry.company ?? '\u2014'}</td>
                <td className="py-1 pr-2">{entry.address ?? '\u2014'}</td>
                <td className="py-1">{entry.date_of_effect ?? '\u2014'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ClassificationSection({
  status,
  surveys,
}: {
  status: any[];
  surveys: any[];
}) {
  return (
    <div className="space-y-3">
      {status.length > 0 && (
        <div>
          <h5 className="text-xs text-gray-500 mb-1">Status</h5>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-[#1F2937]">
                <th className="text-left py-1 pr-2">Society</th>
                <th className="text-left py-1 pr-2">Date</th>
                <th className="text-left py-1 pr-2">Status</th>
                <th className="text-left py-1">Reason</th>
              </tr>
            </thead>
            <tbody>
              {status.map((entry: any, i: number) => {
                const isWithdrawn =
                  entry.status?.toLowerCase().includes('withdrawn') ?? false;
                return (
                  <tr
                    key={i}
                    className={`border-b border-[#1F2937] ${isWithdrawn ? 'text-amber-400' : 'text-gray-400'}`}
                    data-testid={isWithdrawn ? 'classification-withdrawn' : undefined}
                  >
                    <td className="py-1 pr-2">{entry.society ?? entry.society_name ?? '\u2014'}</td>
                    <td className="py-1 pr-2">{entry.date ?? entry.date_of_status_change ?? '\u2014'}</td>
                    <td className="py-1 pr-2">{entry.status ?? '\u2014'}</td>
                    <td className="py-1">{entry.reason ?? '\u2014'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {surveys.length > 0 && (
        <div>
          <h5 className="text-xs text-gray-500 mb-1">Surveys</h5>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-[#1F2937]">
                <th className="text-left py-1 pr-2">Society</th>
                <th className="text-left py-1 pr-2">Survey Date</th>
                <th className="text-left py-1">Next Survey</th>
              </tr>
            </thead>
            <tbody>
              {surveys.map((entry: any, i: number) => (
                <tr key={i} className="border-b border-[#1F2937] text-gray-400">
                  <td className="py-1 pr-2">{entry.society ?? entry.society_name ?? '\u2014'}</td>
                  <td className="py-1 pr-2">{entry.date ?? entry.date_of_survey ?? '\u2014'}</td>
                  <td className="py-1">{entry.next_date ?? entry.date_of_next_survey ?? '\u2014'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SafetyCertificatesTable({ entries }: { entries: any[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-[#1F2937]">
            <th className="text-left py-1 pr-2">Society</th>
            <th className="text-left py-1 pr-2">Survey Date</th>
            <th className="text-left py-1 pr-2">Expiry</th>
            <th className="text-left py-1 pr-2">Status</th>
            <th className="text-left py-1">Type</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry: any, i: number) => (
            <tr key={i} className="border-b border-[#1F2937] text-gray-400">
              <td className="py-1 pr-2">{entry.society ?? '\u2014'}</td>
              <td className="py-1 pr-2">{entry.date_of_survey ?? entry.survey_date ?? '\u2014'}</td>
              <td className="py-1 pr-2">{entry.date_of_expiry ?? entry.expiry ?? '\u2014'}</td>
              <td className="py-1 pr-2">{entry.status ?? '\u2014'}</td>
              <td className="py-1">{entry.type ?? entry.reason ?? '\u2014'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PscInspectionsTable({ entries }: { entries: any[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-[#1F2937]">
            <th className="text-left py-1 pr-2">Authority</th>
            <th className="text-left py-1 pr-2">Port</th>
            <th className="text-left py-1 pr-2">Date</th>
            <th className="text-left py-1 pr-2">Detention</th>
            <th className="text-left py-1 pr-2">PSC Org</th>
            <th className="text-left py-1 pr-2">Type</th>
            <th className="text-left py-1 pr-2">Duration</th>
            <th className="text-left py-1">Deficiencies</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry: any, i: number) => {
            const isDetention =
              entry.detention === 'Y' || entry.detention === true || entry.detained === true;
            const defCount =
              typeof entry.deficiencies === 'number'
                ? entry.deficiencies
                : typeof entry.number_of_deficiencies === 'number'
                  ? entry.number_of_deficiencies
                  : null;
            return (
              <tr
                key={i}
                className={`border-b border-[#1F2937] ${isDetention ? 'text-red-400 font-medium' : 'text-gray-400'}`}
                data-testid={isDetention ? 'psc-detention-row' : undefined}
              >
                <td className="py-1 pr-2">{entry.authority ?? entry.country ?? '\u2014'}</td>
                <td className="py-1 pr-2">{entry.port ?? '\u2014'}</td>
                <td className="py-1 pr-2">{entry.date ?? '\u2014'}</td>
                <td className="py-1 pr-2">{isDetention ? 'Yes' : 'No'}</td>
                <td className="py-1 pr-2">{entry.psc_organisation ?? entry.psc_org ?? '\u2014'}</td>
                <td className="py-1 pr-2">{entry.type_of_inspection ?? entry.type ?? '\u2014'}</td>
                <td className="py-1 pr-2">
                  {entry.duration_days ?? entry.duration ?? '\u2014'}
                </td>
                <td className={`py-1 ${defCount !== null ? getDeficiencyColor(defCount) : ''}`}>
                  {defCount ?? '\u2014'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function NameHistoryList({ entries }: { entries: any[] }) {
  return (
    <ul className="space-y-1 text-xs">
      {entries.map((entry: any, i: number) => (
        <li key={i} className="text-gray-400">
          <span className="text-gray-300 font-medium">{entry.name ?? '\u2014'}</span>
          {entry.date_of_effect && (
            <span className="ml-2 text-gray-500">{entry.date_of_effect}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function FlagHistoryList({ entries }: { entries: any[] }) {
  return (
    <ul className="space-y-1 text-xs">
      {entries.map((entry: any, i: number) => {
        const flag = entry.flag ?? entry.name ?? '\u2014';
        const isFoc = isFlagOfConvenience(flag);
        return (
          <li key={i} className="text-gray-400" data-testid={isFoc ? 'foc-flag' : undefined}>
            <span className={`font-medium ${isFoc ? 'text-amber-400' : 'text-gray-300'}`}>
              {flag}
            </span>
            {entry.date_of_effect && (
              <span className="ml-2 text-gray-500">{entry.date_of_effect}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function CompanyHistoryList({ entries }: { entries: any[] }) {
  return (
    <ul className="space-y-1 text-xs">
      {entries.map((entry: any, i: number) => (
        <li key={i} className="text-gray-400">
          <span className="text-gray-300 font-medium">
            {entry.company_name ?? entry.company ?? '\u2014'}
          </span>
          {entry.role && <span className="ml-2 text-gray-500">({entry.role})</span>}
          {entry.date_of_effect && (
            <span className="ml-2 text-gray-500">{entry.date_of_effect}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function EquasisSection({ mmsi, equasis }: EquasisSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedUploadId, setSelectedUploadId] = useState<number | null>(null);
  const [historicalData, setHistoricalData] = useState<Record<string, any> | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  if (!equasis) {
    return (
      <CollapsibleSection title="Equasis Data" testId="equasis-section">
        <p className="text-xs text-gray-500" data-testid="equasis-empty">
          No Equasis data {'\u2014'} Upload a Ship Folder PDF to enrich this vessel
        </p>
      </CollapsibleSection>
    );
  }

  const latestUpload = equasis.uploads[0];
  const displayData = selectedUploadId && historicalData ? historicalData : equasis.latest;

  const handleUploadSelect = async (uploadId: number) => {
    if (uploadId === latestUpload?.id) {
      setSelectedUploadId(null);
      setHistoricalData(null);
      return;
    }
    setSelectedUploadId(uploadId);
    setLoadingHistory(true);
    try {
      const res = await fetch(`/api/equasis/${mmsi}/upload/${uploadId}`);
      if (res.ok) {
        const data = await res.json();
        setHistoricalData(data);
      }
    } catch {
      // Silently fail, keep showing latest
    } finally {
      setLoadingHistory(false);
    }
  };

  const shipParticulars = displayData.ship_particulars ?? {};
  const management = displayData.management ?? [];
  const classificationStatus = displayData.classification_status ?? [];
  const classificationSurveys = displayData.classification_surveys ?? [];
  const safetyCertificates = displayData.safety_certificates ?? [];
  const pscInspections = displayData.psc_inspections ?? [];
  const nameHistory = displayData.name_history ?? [];
  const flagHistory = displayData.flag_history ?? [];
  const companyHistory = displayData.company_history ?? [];

  return (
    <CollapsibleSection title="Equasis Data" testId="equasis-section">
      {/* Summary line */}
      <p className="text-xs text-gray-400 mb-2" data-testid="equasis-summary">
        Last uploaded: {formatUploadDate(latestUpload.upload_timestamp)}
        {latestUpload.edition_date && ` \u2014 ${latestUpload.edition_date} edition`}
      </p>

      {/* Previous uploads dropdown */}
      {equasis.upload_count > 1 && (
        <div className="mb-2">
          <select
            data-testid="equasis-previous-uploads"
            value={selectedUploadId ?? latestUpload?.id ?? ''}
            onChange={(e) => handleUploadSelect(Number(e.target.value))}
            className="bg-gray-800 text-gray-300 text-xs rounded px-2 py-1 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
          >
            {equasis.uploads.map((upload) => (
              <option key={upload.id} value={upload.id}>
                {formatUploadDate(upload.upload_timestamp)}
                {upload.edition_date ? ` (${upload.edition_date})` : ''}
                {upload.id === latestUpload.id ? ' (latest)' : ''}
              </option>
            ))}
          </select>
          {loadingHistory && (
            <span className="ml-2 text-xs text-gray-500">Loading...</span>
          )}
        </div>
      )}

      {/* Expand button */}
      <button
        data-testid="equasis-expand-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mb-2"
      >
        <span>{isExpanded ? '\u25B2' : '\u25BC'}</span>
        <span>{isExpanded ? 'Collapse vessel information' : 'Expand vessel information'}</span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="space-y-0" data-testid="equasis-expanded">
          <CollapsibleSubsection title="Ship Particulars" testId="equasis-ship-particulars">
            <ShipParticulars data={shipParticulars} />
          </CollapsibleSubsection>

          {management.length > 0 && (
            <CollapsibleSubsection title="Management" testId="equasis-management">
              <ManagementTable entries={management} />
            </CollapsibleSubsection>
          )}

          {(classificationStatus.length > 0 || classificationSurveys.length > 0) && (
            <CollapsibleSubsection title="Classification" testId="equasis-classification">
              <ClassificationSection
                status={classificationStatus}
                surveys={classificationSurveys}
              />
            </CollapsibleSubsection>
          )}

          {safetyCertificates.length > 0 && (
            <CollapsibleSubsection title="Safety Certificates" testId="equasis-safety-certificates">
              <SafetyCertificatesTable entries={safetyCertificates} />
            </CollapsibleSubsection>
          )}

          {pscInspections.length > 0 && (
            <CollapsibleSubsection title="PSC Inspections" testId="equasis-psc-inspections">
              <PscInspectionsTable entries={pscInspections} />
            </CollapsibleSubsection>
          )}

          {nameHistory.length > 0 && (
            <CollapsibleSubsection title="Name History" testId="equasis-name-history">
              <NameHistoryList entries={nameHistory} />
            </CollapsibleSubsection>
          )}

          {flagHistory.length > 0 && (
            <CollapsibleSubsection title="Flag History" testId="equasis-flag-history">
              <FlagHistoryList entries={flagHistory} />
            </CollapsibleSubsection>
          )}

          {companyHistory.length > 0 && (
            <CollapsibleSubsection title="Company History" testId="equasis-company-history">
              <CompanyHistoryList entries={companyHistory} />
            </CollapsibleSubsection>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}
