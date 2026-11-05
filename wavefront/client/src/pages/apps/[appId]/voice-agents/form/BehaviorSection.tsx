import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { useFormContext } from 'react-hook-form';
import { VoiceAgentInput } from './voice-agent-form';

const BehaviorSection = () => {
  const form = useFormContext<VoiceAgentInput>();

  return (
    <>
      <FormField
        control={form.control}
        name="system_prompt"
        render={({ field }) => (
          <FormItem className="flex min-h-0 flex-[2] flex-col gap-2">
            <FormLabel>
              System Prompt<span className="text-red-500">*</span>
            </FormLabel>
            <div className="relative min-h-0 flex-1">
              <FormControl>
                <textarea
                  placeholder="You are a helpful customer support agent. Answer questions politely and professionally..."
                  className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring absolute inset-0 h-full w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                  {...field}
                />
              </FormControl>
            </div>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="welcome_message"
        render={({ field }) => (
          <FormItem className="flex min-h-0 flex-1 flex-col gap-2">
            <FormLabel>Welcome Message</FormLabel>
            <div className="relative min-h-0 flex-1">
              <FormControl>
                <textarea
                  placeholder="Optional. Leave blank to skip the greeting. Example: Hello! How can I help you today?"
                  className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring absolute inset-0 h-full w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                  {...field}
                />
              </FormControl>
            </div>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
};

export default BehaviorSection;
