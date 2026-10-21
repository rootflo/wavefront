import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { useGetVoiceAgent } from '@app/hooks';
import { cn } from '@app/lib/utils';
import { VoiceAgent, VoiceAgentListItem } from '@app/types/voice-agent';
import { Globe, Phone } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import BrowserCallDialog from './BrowserCallDialog';
import OutboundCallDialog from './OutboundCallDialog';

interface VoiceAgentOperationsDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** Table-row summary — popup opens immediately; full detail loads inside. */
  agentSummary: VoiceAgentListItem;
  appId: string;
}

const EMPTY_DETAIL_FIELDS: Pick<
  VoiceAgent,
  | 'llm_config_id'
  | 'tts_config_id'
  | 'stt_config_id'
  | 'telephony_config_id'
  | 'system_prompt'
  | 'welcome_message'
  | 'tts_voice_ids'
  | 'tts_parameters'
  | 'stt_parameters'
  | 'conversation_config'
  | 'inbound_numbers'
  | 'outbound_numbers'
> = {
  llm_config_id: '',
  tts_config_id: '',
  stt_config_id: '',
  telephony_config_id: '',
  system_prompt: '',
  welcome_message: '',
  tts_voice_ids: {},
  tts_parameters: null,
  stt_parameters: null,
  conversation_config: null,
  inbound_numbers: [],
  outbound_numbers: [],
};

/**
 * Combined operations popup: browser (WebRTC) call and outbound telephony call.
 * Opens immediately from the list row; action buttons stay disabled until detail loads.
 */
const VoiceAgentOperationsDialog: React.FC<VoiceAgentOperationsDialogProps> = ({
  isOpen,
  onOpenChange,
  agentSummary,
  appId,
}) => {
  const [tab, setTab] = useState<'browser' | 'phone'>('phone');
  const { data: agentDetail, isLoading } = useGetVoiceAgent(appId, isOpen ? agentSummary.id : undefined);
  const detailReady = !!agentDetail && !isLoading;

  const agent: VoiceAgent = useMemo(
    () => ({
      ...EMPTY_DETAIL_FIELDS,
      ...agentSummary,
      ...(agentDetail || {}),
    }),
    [agentSummary, agentDetail]
  );

  const handleOpenChange = (open: boolean) => {
    if (!open) setTab('phone');
    onOpenChange(open);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="flex h-[520px] max-w-md flex-col gap-4 overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle>Talk to agent</DialogTitle>
          <DialogDescription>
            Speak with <strong>{agentSummary.name}</strong> in the browser or over the phone
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as 'browser' | 'phone')}
          className="flex min-h-0 flex-1 flex-col gap-3"
        >
          <TabsList className="grid w-full shrink-0 grid-cols-2">
            <TabsTrigger value="phone" className="gap-0">
              <span className="inline-flex flex-row items-center gap-1.5">
                <Phone className="h-3.5 w-3.5 shrink-0" />
                <span>Phone</span>
              </span>
            </TabsTrigger>
            <TabsTrigger value="browser" className="gap-0">
              <span className="inline-flex flex-row items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 shrink-0" />
                <span>Browser</span>
              </span>
            </TabsTrigger>
          </TabsList>

          <div className="relative min-h-0 flex-1 overflow-hidden">
            <TabsContent
              value="phone"
              className={cn('absolute inset-0 mt-0 flex flex-col overflow-y-auto', tab !== 'phone' && 'hidden')}
            >
              <OutboundCallDialog
                isOpen={isOpen && tab === 'phone'}
                onOpenChange={handleOpenChange}
                agent={agent}
                embedded
                actionsDisabled={!detailReady}
              />
            </TabsContent>

            <TabsContent
              value="browser"
              forceMount
              className={cn(
                'absolute inset-0 mt-0 flex flex-col overflow-y-auto',
                tab !== 'browser' && 'pointer-events-none invisible'
              )}
            >
              <BrowserCallDialog
                isOpen={isOpen}
                onOpenChange={handleOpenChange}
                agent={agent}
                appId={appId}
                embedded
                actionsDisabled={!detailReady}
              />
            </TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};

export default VoiceAgentOperationsDialog;
