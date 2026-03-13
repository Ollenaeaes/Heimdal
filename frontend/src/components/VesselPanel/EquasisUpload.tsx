import { useRef, useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

export const EQUASIS_TOAST_DURATION_MS = 3000;

export interface EquasisUploadResponse {
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

export function buildSuccessToast(data: EquasisUploadResponse): string {
  return `Equasis data imported: ${data.ship_name} (IMO ${data.imo}) — ${data.summary.psc_inspections} PSC inspections, ${data.summary.flag_changes} flag changes, ${data.summary.companies} companies extracted`;
}

export async function uploadEquasisPdf(mmsi: number, file: File): Promise<EquasisUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`/api/equasis/upload?mmsi=${mmsi}`, {
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
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (file: File) => uploadEquasisPdf(mmsi, file),
    onSuccess: (data) => {
      setToast({ type: 'success', message: buildSuccessToast(data) });
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      mutation.mutate(file);
    }
    // Reset input so the same file can be re-selected
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="px-4 py-3 border-b border-gray-700" data-testid="equasis-upload-section">
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

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        data-testid="equasis-file-input"
        className="hidden"
        onChange={handleFileChange}
      />

      <button
        data-testid="equasis-upload-button"
        onClick={() => fileInputRef.current?.click()}
        disabled={mutation.isPending}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-sm font-medium rounded px-3 py-2 transition-colors"
      >
        {mutation.isPending ? 'Parsing...' : 'Upload Equasis PDF'}
      </button>
    </div>
  );
}
