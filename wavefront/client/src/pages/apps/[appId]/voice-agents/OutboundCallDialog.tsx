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
import { useGetTelephonyConfig } from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { VoiceAgent } from '@app/types/voice-agent';
import React, { useState } from 'react';

interface OutboundCallDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  agent: VoiceAgent;
}

const OutboundCallDialog: React.FC<OutboundCallDialogProps> = ({ isOpen, onOpenChange, appId, agent }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState('');
  const [callLoading, setCallLoading] = useState(false);

  // Fetch the specific telephony config to get phone numbers for call initiation
  const { data: currentTelephonyConfig } = useGetTelephonyConfig(appId, agent.telephony_config_id);
  const availablePhoneNumbers = currentTelephonyConfig?.phone_numbers || [];

  // E.164 phone number validation
  const isValidE164PhoneNumber = (phoneNumber: string): boolean => {
    // E.164 format: +[1-15 digits]
    const e164Regex = /^\+[1-9]\d{1,14}$/;
    return e164Regex.test(phoneNumber);
  };

  const handleInitiateCall = async () => {
    if (!toNumber.trim()) {
      notifyError('Please enter a destination phone number');
      return;
    }

    if (!isValidE164PhoneNumber(toNumber.trim())) {
      notifyError('Invalid phone number format. Use E.164 format (e.g., +14155559999)');
      return;
    }

    if (fromNumber.trim() && !isValidE164PhoneNumber(fromNumber.trim())) {
      notifyError('Invalid from number format. Use E.164 format (e.g., +14155551234)');
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
      const callInfo = response?.data?.data?.call;

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

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Initiate Outbound Call</DialogTitle>
          <DialogDescription>
            Make an outbound call using <strong>{agent.name}</strong>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* To Number */}
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
            <p className="text-xs text-gray-500">Destination phone number in E.164 format</p>
          </div>

          {/* From Number */}
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
            <p className="text-xs text-gray-500">
              {availablePhoneNumbers.length > 0
                ? 'Select from configured phone numbers or leave empty for auto-select'
                : 'Source phone number in E.164 format (leave empty to use first configured number)'}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose} disabled={callLoading}>
            Cancel
          </Button>
          <Button type="button" onClick={handleInitiateCall} disabled={callLoading} loading={callLoading}>
            Make Call
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default OutboundCallDialog;
