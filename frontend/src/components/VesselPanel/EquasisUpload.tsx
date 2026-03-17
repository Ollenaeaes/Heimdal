import { useRef, useState, useEffect, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CollapsibleSection } from './CollapsibleSection';

export const EQUASIS_TOAST_DURATION_MS = 5000;

export interface ShipFolderResponse {
  document_type: 'ship_folder';
  mmsi: number;
  imo: number;
  ship_name: string;
  created: boolean;
  equasis_data_id: number;
  summary: {
    psc_inspections: number;
    flag_changes: number;
    companies: number;
    classification_entries: number;
    name_changes: number;
  };
}

export interface CompanyFolderResponse {
  document_type: 'company_folder';
  upload_id: number;
  company_imo: string;
  company_name: string;
  fleet_size: number;
  vessels_created: number;
  vessels_updated: number;
  network_edges_created: number;
  fleet: Array<{
    imo: number;
    mmsi: number;
    name: string;
    type: string;
    flag: string;
    status: 'new' | 'updated';
  }>;
  scoring_triggered_for: number;
}

export type EquasisUploadResponse = ShipFolderResponse | CompanyFolderResponse;

export function buildSuccessToast(data: EquasisUploadResponse): string {
  if (data.document_type === 'company_folder') {
    return `Fleet discovered: ${data.company_name} — ${data.fleet_size} vessels, ${data.vessels_created} new, ${data.network_edges_created} ownership edges created`;
  }
  return `Equasis data imported: ${data.ship_name} (IMO ${data.imo}) — ${data.summary.psc_inspections} PSC inspections, ${data.summary.flag_changes} flag changes, ${data.summary.companies} companies extracted`;
}

export async function uploadEquasisPdf(file: File, mmsi?: number): Promise<EquasisUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const url = mmsi ? `/api/equasis/upload?mmsi=${mmsi}` : '/api/equasis/upload';
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Upload failed: ${res.status}`);
  }

  return res.json();
}

interface EquasisUploadProps {
  mmsi: number;
}

export function EquasisUpload({ mmsi }: EquasisUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [lastResult, setLastResult] = useState<EquasisUploadResponse | null>(null);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (file: File) => uploadEquasisPdf(file, mmsi),
    onSuccess: (data) => {
      setToast({ type: 'success', message: buildSuccessToast(data) });
      setLastResult(data);
      queryClient.invalidateQueries({ queryKey: ['vessel', mmsi] });
    },
    onError: (error: Error) => {
      setToast({ type: 'error', message: error.message || 'Failed to upload Equasis PDF.' });
    },
  });

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), EQUASIS_TOAST_DURATION_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  const handleFiles = useCallback((files: FileList | File[]) => {
    const fileArray = Array.from(files);
    for (const file of fileArray) {
      if (file.type === 'application/pdf' || file.name.endsWith('.pdf')) {
        mutation.mutate(file);
      }
    }
  }, [mutation]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) handleFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  return (
    <CollapsibleSection title="Equasis Upload" testId="equasis-upload-section">
      {/* Toast */}
      {toast && (
        <div
          data-testid="equasis-upload-toast"
          className={`absolute top-14 right-4 left-4 z-60 rounded px-3 py-2 text-sm font-medium shadow-lg ${
            toast.type === 'success'
              ? 'bg-green-800 text-green-200'
              : 'bg-red-800 text-red-200'
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* Drop zone */}
      <div
        ref={dropZoneRef}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        data-testid="equasis-drop-zone"
        className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
          isDragging
            ? 'border-blue-400 bg-blue-900/20'
            : 'border-gray-600 hover:border-gray-500 hover:bg-gray-800/30'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          multiple
          data-testid="equasis-file-input"
          className="hidden"
          onChange={handleFileChange}
        />

        {mutation.isPending ? (
          <div className="text-sm text-blue-400">
            <span className="animate-pulse">Parsing PDF...</span>
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-400">
              Drop ship folder and/or company folder PDFs here, or click to browse
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Accepted: Equasis ship folder PDF, Equasis company folder PDF
            </p>
          </>
        )}
      </div>

      {/* Extraction summary */}
      {lastResult && (
        <div className="mt-3 rounded bg-gray-800/50 p-3 text-xs" data-testid="equasis-upload-summary">
          {lastResult.document_type === 'company_folder' ? (
            <CompanyFolderSummary data={lastResult} />
          ) : (
            <ShipFolderSummary data={lastResult} />
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}

function ShipFolderSummary({ data }: { data: ShipFolderResponse }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-green-400 font-medium">
        <span>Ship folder processed</span>
      </div>
      <p className="text-gray-300">
        {data.ship_name} (IMO {data.imo})
      </p>
      <ul className="text-gray-400 space-y-0.5 ml-2">
        <li>{data.summary.flag_changes} flag changes extracted</li>
        <li>{data.summary.name_changes} name changes extracted</li>
        <li>{data.summary.companies} management changes extracted</li>
        <li>{data.summary.psc_inspections} PSC inspections extracted</li>
        <li>{data.summary.classification_entries} classification entries</li>
      </ul>
    </div>
  );
}

function CompanyFolderSummary({ data }: { data: CompanyFolderResponse }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-green-400 font-medium">
        <span>Company folder processed</span>
      </div>
      <p className="text-gray-300">{data.company_name}</p>
      <ul className="text-gray-400 space-y-0.5 ml-2">
        <li>{data.fleet_size} vessels in fleet</li>
        <li>{data.vessels_created} new vessels added to Heimdal</li>
        <li>{data.vessels_updated} existing vessels updated</li>
        <li>{data.network_edges_created} ownership network edges created</li>
      </ul>
      {data.fleet.length > 0 && (
        <div className="mt-2 max-h-32 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="text-left py-0.5">IMO</th>
                <th className="text-left py-0.5">Name</th>
                <th className="text-left py-0.5">Type</th>
                <th className="text-left py-0.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.fleet.map((v) => (
                <tr key={v.imo} className="text-gray-400">
                  <td className="py-0.5 font-mono">{v.imo}</td>
                  <td className="py-0.5">{v.name}</td>
                  <td className="py-0.5">{v.type}</td>
                  <td className={`py-0.5 ${v.status === 'new' ? 'text-blue-400' : 'text-gray-400'}`}>
                    {v.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-gray-500 mt-1">
        Risk scoring triggered for {data.scoring_triggered_for} vessels
      </p>
    </div>
  );
}
