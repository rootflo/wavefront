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
import React, { useState } from 'react';

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

    setCallLoading(true);
    try {
      const callData: { to_number: string; from_number?: string } = {
        to_number: toNumber.trim(),
      };

      if (fromNumber.trim()) {
        callData.from_number = fromNumber.trim();
      }

      const response = await floConsoleService.voiceAgentService.initiateCall(agent.id, callData);
      const callInfo = (response?.data?.data as { call?: CallInfo })?.call;

      notifySuccess(
        `Call initiated successfully! Call SID: ${callInfo?.call_sid || 'N/A'}, Status: ${callInfo?.status || 'queued'}`
      );

      // Reset form and close dialog
      setToNumber('');
      setFromNumber('');
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
    onOpenChange(false);
  };

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
