import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { VoiceAgent } from '@app/types/voice-agent';
import { Plus, X } from 'lucide-react';
import React, { useState } from 'react';
import { ContextRow, contextFromRows } from './outbound-call-context';

interface CallInfo {
  call_sid?: string;
  status?: string;
}

interface OutboundCallDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  agent: VoiceAgent;
  /** When true, render panel content only (parent owns the Dialog shell). */
  embedded?: boolean;
  /** Disable Make Call until agent detail (e.g. outbound numbers) has loaded. */
  actionsDisabled?: boolean;
}

const OutboundCallDialog: React.FC<OutboundCallDialogProps> = ({
  isOpen,
  onOpenChange,
  agent,
  embedded = false,
  actionsDisabled = false,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState('');
  const [contextRows, setContextRows] = useState<ContextRow[]>([]);
  const [callLoading, setCallLoading] = useState(false);

  // Get outbound phone numbers from the voice agent (not telephony config)
  const availablePhoneNumbers = agent.outbound_numbers || [];

  const handleInitiateCall = async () => {
    if (actionsDisabled) return;
    if (!toNumber.trim()) {
      notifyError('Please enter a destination phone number');
      return;
    }

    if (agent.status !== 'active') {
      notifyError('Voice agent must be active to initiate calls');
      return;
    }

    const { context, error: contextError } = contextFromRows(contextRows);
    if (contextError) {
      notifyError(contextError);
      return;
    }

    setCallLoading(true);
    try {
      const callData: { to_number: string; from_number?: string; context?: Record<string, string> } = {
        to_number: toNumber.trim(),
      };

      if (fromNumber.trim()) {
        callData.from_number = fromNumber.trim();
      }
      if (context) {
        callData.context = context;
      }

      const response = await floConsoleService.voiceAgentService.initiateCall(agent.id, callData);
      const callInfo = (response?.data?.data as { call?: CallInfo })?.call;

      notifySuccess(
        `Call initiated successfully! Call SID: ${callInfo?.call_sid || 'N/A'}, Status: ${callInfo?.status || 'queued'}`
      );

      // Reset form and close dialog
      setToNumber('');
      setFromNumber('');
      setContextRows([]);
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to initiate call');
    } finally {
      setCallLoading(false);
    }
  };

  const handleClose = () => {
    setToNumber('');
    setFromNumber('');
    setContextRows([]);
    onOpenChange(false);
  };

  const updateContextRow = (index: number, change: Partial<ContextRow>) =>
    setContextRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...change } : row)));

  const body = (
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <Label htmlFor="to-number">
          To Number <span className="text-red-500">*</span>
        </Label>
        <Input
          id="to-number"
          type="text"
          value={toNumber}
          onChange={(e) => setToNumber(e.target.value)}
          placeholder="+14155559999"
        />
        <p className="frost-text-muted text-xs">Destination phone number in E.164 format</p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="from-number">From Number (Optional)</Label>
        {availablePhoneNumbers.length > 0 ? (
          <Select value={fromNumber || undefined} onValueChange={setFromNumber}>
            <SelectTrigger id="from-number">
              <SelectValue placeholder="Auto-select (use first configured number)" />
            </SelectTrigger>
            <SelectContent>
              {availablePhoneNumbers.map((phone) => (
                <SelectItem key={phone} value={phone}>
                  {phone}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            id="from-number"
            type="text"
            value={fromNumber}
            onChange={(e) => setFromNumber(e.target.value)}
            placeholder="+14155551234"
          />
        )}
        <p className="frost-text-muted text-xs">
          {availablePhoneNumbers.length > 0
            ? 'Select from configured phone numbers or leave empty for auto-select'
            : 'Source phone number in E.164 format (leave empty to use first configured number)'}
        </p>
      </div>

      <div className="space-y-2">
        <Label>Caller context (optional, for testing)</Label>
        <p className="frost-text-muted text-xs">
          What a CRM would send with this call. The agent knows it from the first line, and tools can use it as
          outbound.&lt;key&gt;.
        </p>
        {contextRows.map((row, index) => (
          <div key={index} className="flex items-center gap-2">
            <Input
              aria-label={`Context key ${index + 1}`}
              value={row.key}
              onChange={(e) => updateContextRow(index, { key: e.target.value })}
              placeholder="reason_for_call"
              className="w-2/5"
            />
            <Input
              aria-label={`Context value ${index + 1}`}
              value={row.value}
              onChange={(e) => updateContextRow(index, { value: e.target.value })}
              placeholder="overdue bill"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              title="Remove"
              onClick={() => setContextRows((rows) => rows.filter((_, i) => i !== index))}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setContextRows((rows) => [...rows, { key: '', value: '' }])}
        >
          <Plus className="mr-1 h-4 w-4" />
          Add context
        </Button>
      </div>
    </div>
  );

  const footer = (
    <div className="mt-auto flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      {!embedded && (
        <Button type="button" variant="outline" onClick={handleClose} disabled={callLoading}>
          Cancel
        </Button>
      )}
      <Button
        type="button"
        onClick={handleInitiateCall}
        disabled={actionsDisabled || callLoading}
        loading={callLoading}
      >
        Make Call
      </Button>
    </div>
  );

  if (embedded) {
    if (!isOpen) return null;
    return (
      <div className="flex h-full min-h-0 flex-col">
        {body}
        {footer}
      </div>
    );
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Initiate Outbound Call</DialogTitle>
          <DialogDescription>
            Make an outbound call using <strong>{agent.name}</strong>
          </DialogDescription>
        </DialogHeader>
        {body}
        <DialogFooter>{footer}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default OutboundCallDialog;
