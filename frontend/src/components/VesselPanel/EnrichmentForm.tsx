import { useState, useEffect, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { EnrichmentPayload } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

export const SOURCE_OPTIONS = [
  'Equasis',
  'Paris MoU',
  'Tokyo MoU',
  'Corporate Registry',
  'Other',
] as const;

export const PI_TIER_OPTIONS = [
  'ig_member',
  'non_ig_western',
  'russian_state',
  'unknown',
  'fraudulent',
  'none',
] as const;

export type PiTier = (typeof PI_TIER_OPTIONS)[number];

export interface EnrichmentFormState {
  source: string;
  registeredOwner: string;
  commercialManager: string;
  beneficialOwner: string;
  piInsurer: string;
  piInsurerTier: PiTier | '';
  classificationSociety: string;
  iacsMember: boolean;
  pscDetentions: string;
  pscDeficiencies: string;
  notes: string;
}

export function getInitialFormState(): EnrichmentFormState {
  return {
    source: '',
    registeredOwner: '',
    commercialManager: '',
    beneficialOwner: '',
    piInsurer: '',
    piInsurerTier: '',
    classificationSociety: '',
    iacsMember: false,
    pscDetentions: '',
    pscDeficiencies: '',
    notes: '',
  };
}

export function isSourceRequired(source: string): boolean {
  return source.trim().length > 0;
}

export function buildPayload(state: EnrichmentFormState): EnrichmentPayload {
  const payload: EnrichmentPayload = {
    source: state.source,
  };

  if (state.registeredOwner || state.commercialManager || state.beneficialOwner) {
    payload.ownership_chain = {};
    if (state.registeredOwner) payload.ownership_chain.registered_owner = state.registeredOwner;
    if (state.commercialManager) payload.ownership_chain.commercial_manager = state.commercialManager;
    if (state.beneficialOwner) payload.ownership_chain.beneficial_owner = state.beneficialOwner;
  }

  if (state.piInsurer) payload.pi_insurer = state.piInsurer;
  if (state.piInsurerTier) payload.pi_insurer_tier = state.piInsurerTier as PiTier;
  if (state.classificationSociety) payload.classification_society = state.classificationSociety;
  if (state.iacsMember) payload.classification_iacs = true;
  if (state.pscDetentions) payload.psc_detentions = parseInt(state.pscDetentions, 10);
  if (state.pscDeficiencies) payload.psc_deficiencies = parseInt(state.pscDeficiencies, 10);
  if (state.notes) payload.notes = state.notes;

  return payload;
}

async function submitEnrichment(mmsi: number, payload: EnrichmentPayload): Promise<void> {
  const res = await fetch(`/api/vessels/${mmsi}/enrich`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Failed to submit enrichment: ${res.status}`);
  }
}

export const TOAST_DURATION_MS = 3000;

interface EnrichmentFormProps {
  mmsi: number;
}

export function EnrichmentForm({ mmsi }: EnrichmentFormProps) {
  const [form, setForm] = useState<EnrichmentFormState>(getInitialFormState);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (payload: EnrichmentPayload) => submitEnrichment(mmsi, payload),
    onSuccess: () => {
      setToast({ type: 'success', message: 'Enrichment data saved. Risk score recalculated.' });
      queryClient.invalidateQueries({ queryKey: ['vessel', mmsi] });
      setForm(getInitialFormState());
    },
    onError: (error: Error) => {
      setToast({ type: 'error', message: error.message || 'Failed to save enrichment data.' });
    },
  });

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), TOAST_DURATION_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  const updateField = useCallback(
    <K extends keyof EnrichmentFormState>(key: K, value: EnrichmentFormState[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const handleSubmit = () => {
    if (!isSourceRequired(form.source)) return;
    const payload = buildPayload(form);
    mutation.mutate(payload);
  };

  return (
    <CollapsibleSection title="Manual Enrichment" testId="enrichment-form-section">
      {/* Toast */}
      {toast && (
        <div
          data-testid="enrichment-toast"
          className={`absolute top-14 right-4 left-4 z-60 rounded px-3 py-2 text-sm font-medium shadow-lg ${
            toast.type === 'success'
              ? 'bg-green-800 text-green-200'
              : 'bg-red-800 text-red-200'
          }`}
        >
          {toast.message}
        </div>
      )}

        <div className="space-y-3" data-testid="enrichment-form-body">
          {/* Source (required) */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Source *</label>
            <select
              data-testid="enrichment-source"
              value={form.source}
              onChange={(e) => updateField('source', e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            >
              <option value="">Select source...</option>
              {SOURCE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>

          {/* Registered Owner */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Registered Owner</label>
            <input
              type="text"
              data-testid="enrichment-registered-owner"
              value={form.registeredOwner}
              onChange={(e) => updateField('registeredOwner', e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Commercial Manager */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Commercial Manager</label>
            <input
              type="text"
              data-testid="enrichment-commercial-manager"
              value={form.commercialManager}
              onChange={(e) => updateField('commercialManager', e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Beneficial Owner */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Beneficial Owner</label>
            <input
              type="text"
              data-testid="enrichment-beneficial-owner"
              value={form.beneficialOwner}
              onChange={(e) => updateField('beneficialOwner', e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* P&I Insurer */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">P&I Insurer</label>
            <input
              type="text"
              data-testid="enrichment-pi-insurer"
              value={form.piInsurer}
              onChange={(e) => updateField('piInsurer', e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* P&I Insurer Tier */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">P&I Insurer Tier</label>
            <select
              data-testid="enrichment-pi-tier"
              value={form.piInsurerTier}
              onChange={(e) => updateField('piInsurerTier', e.target.value as PiTier | '')}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            >
              <option value="">Select tier...</option>
              {PI_TIER_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>

          {/* Classification Society */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Classification Society</label>
            <input
              type="text"
              data-testid="enrichment-classification-society"
              value={form.classificationSociety}
              onChange={(e) => updateField('classificationSociety', e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* IACS Member */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              data-testid="enrichment-iacs-member"
              checked={form.iacsMember}
              onChange={(e) => updateField('iacsMember', e.target.checked)}
              className="rounded bg-gray-800 border-gray-600"
            />
            <label className="text-xs text-gray-400">IACS Member</label>
          </div>

          {/* PSC Detentions */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">PSC Detentions</label>
            <input
              type="number"
              data-testid="enrichment-psc-detentions"
              value={form.pscDetentions}
              onChange={(e) => updateField('pscDetentions', e.target.value)}
              min="0"
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* PSC Deficiencies */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">PSC Deficiencies</label>
            <input
              type="number"
              data-testid="enrichment-psc-deficiencies"
              value={form.pscDeficiencies}
              onChange={(e) => updateField('pscDeficiencies', e.target.value)}
              min="0"
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Notes</label>
            <textarea
              data-testid="enrichment-notes"
              value={form.notes}
              onChange={(e) => updateField('notes', e.target.value)}
              rows={3}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-[#1F2937] focus:border-blue-500 focus:outline-none resize-none"
            />
          </div>

          {/* Submit */}
          <button
            data-testid="enrichment-submit"
            onClick={handleSubmit}
            disabled={!isSourceRequired(form.source) || mutation.isPending}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-sm font-medium rounded px-3 py-2 transition-colors"
          >
            {mutation.isPending ? 'Submitting...' : 'Submit Enrichment'}
          </button>
        </div>
    </CollapsibleSection>
  );
}
