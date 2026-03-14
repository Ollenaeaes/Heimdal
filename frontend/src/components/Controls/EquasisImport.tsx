import { useState, useRef, useCallback } from 'react';
import { useVesselStore } from '../../hooks/useVesselStore';

export interface EquasisUploadResponse {
  document_type?: 'ship_folder' | 'company_folder';
  mmsi?: number;
  imo?: number;
  ship_name?: string;
  created?: boolean;
  equasis_data_id?: number;
  summary?: Record<string, unknown>;
  // Company folder fields
  company_imo?: string;
  company_name?: string;
  fleet_size?: number;
  vessels_created?: number;
  vessels_updated?: number;
  network_edges_created?: number;
}

export const ACCEPTED_FILE_TYPE = '.pdf';

/** Build the FormData for an Equasis PDF upload (no mmsi param). */
export function buildUploadFormData(file: File): FormData {
  const fd = new FormData();
  fd.append('file', file);
  return fd;
}

/** Format a user-facing success message based on the upload response. */
export function formatSuccessMessage(res: EquasisUploadResponse): string {
  if (res.document_type === 'company_folder') {
    return `Fleet discovered: ${res.company_name} — ${res.fleet_size} vessels, ${res.vessels_created} new, ${res.network_edges_created} ownership edges`;
  }
  if (res.created) {
    return `New vessel added: ${res.ship_name} (IMO ${res.imo})`;
  }
  return `Equasis data imported for ${res.ship_name}`;
}

export function EquasisImport() {
  const [status, setStatus] = useState<'idle' | 'uploading'>('idle');
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectVessel = useVesselStore((s) => s.selectVessel);

  const showToast = useCallback((type: 'success' | 'error', message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 5000);
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    setStatus('uploading');
    try {
      const fd = buildUploadFormData(file);
      const res = await fetch('/api/equasis/upload', {
        method: 'POST',
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? err.message ?? `Upload failed (${res.status})`);
      }
      const data: EquasisUploadResponse = await res.json();
      showToast('success', formatSuccessMessage(data));
      // Select the vessel for ship folder, or first fleet vessel for company folder
      if (data.mmsi) {
        selectVessel(data.mmsi);
      }
    } catch (e) {
      showToast('error', e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setStatus('idle');
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [selectVessel, showToast]);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleUpload(file);
    },
    [handleUpload],
  );

  return (
    <div className="relative">
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_FILE_TYPE}
        className="hidden"
        data-testid="equasis-file-input"
        onChange={handleFileChange}
      />
      <button
        data-testid="equasis-import-btn"
        disabled={status === 'uploading'}
        onClick={() => fileInputRef.current?.click()}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border border-[#1F2937] ${
          status === 'uploading'
            ? 'bg-[#1F2937] text-gray-400 cursor-wait'
            : 'bg-[#111827] text-gray-300 hover:bg-[#1F2937] hover:text-white'
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-3.5 h-3.5"
        >
          <path
            fillRule="evenodd"
            d="M4.5 2A1.5 1.5 0 003 3.5v13A1.5 1.5 0 004.5 18h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm4.75 11.25a.75.75 0 001.5 0v-2.546l.943.942a.75.75 0 101.06-1.06l-2.22-2.22a.75.75 0 00-1.06 0l-2.22 2.22a.75.75 0 001.06 1.06l.937-.942v2.546z"
            clipRule="evenodd"
          />
        </svg>
        {status === 'uploading' ? 'Uploading...' : 'Import Equasis'}
      </button>

      {toast && (
        <div
          data-testid="equasis-toast"
          className={`absolute top-full left-0 mt-1.5 whitespace-nowrap rounded px-3 py-2 text-xs font-medium shadow-lg z-50 ${
            toast.type === 'success'
              ? 'bg-green-800 text-green-200'
              : 'bg-red-800 text-red-200'
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
