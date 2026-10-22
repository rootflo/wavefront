import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { CONVERSATION_CONFIG_DOCS } from './conversation-config';

/** The Guide tab: what every Advanced option does, its default and range, plus common recipes. */
function ConversationConfigGuide() {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-medium">How the Advanced settings work</h3>
        <p className="frost-text-muted text-xs">
          All values are optional: an option left at its default follows what a bot with no configuration does. Times
          are in milliseconds (1000 ms = 1 second). Values outside the range are clamped to it, and an invalid value is
          ignored in favour of its default.
        </p>
      </div>

      {CONVERSATION_CONFIG_DOCS.map((section) => (
        <div key={section.section} className="space-y-2">
          <div>
            <h4 className="text-sm font-medium">
              {section.title} <code className="frost-text-muted text-xs font-normal">{section.section}</code>
            </h4>
            <p className="frost-text-muted text-xs">{section.summary}</p>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[210px]">Option</TableHead>
                  <TableHead className="w-[90px]">Default</TableHead>
                  <TableHead className="w-[130px]">Allowed</TableHead>
                  <TableHead>What it does</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {section.options.map((option) => (
                  <TableRow key={option.key}>
                    <TableCell className="align-top text-xs">
                      <div className="font-medium">{option.label}</div>
                      <code className="frost-text-muted">{option.key}</code>
                    </TableCell>
                    <TableCell className="align-top text-xs">{option.defaultValue}</TableCell>
                    <TableCell className="align-top text-xs">{option.range}</TableCell>
                    <TableCell className="align-top text-xs whitespace-normal">{option.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ))}

      <div className="space-y-2">
        <h4 className="text-sm font-medium">Examples</h4>
        <ul className="frost-text-muted list-disc space-y-1 pl-5 text-xs">
          <li>
            <b>Bot must finish what it says:</b> turn off <i>Let the user interrupt</i>. Nothing the user says over the
            bot interrupts it.
          </li>
          <li>
            <b>Welcome message must play fully:</b> turn on <i>Play the welcome message fully</i>. Users can still
            interrupt the bot after the welcome.
          </li>
          <li>
            <b>Fewer accidental interruptions:</b> keep barge-in on and set <i>Words needed to interrupt</i> to 2. The
            bot then stops only after two words are heard, not on any sound.
          </li>
          <li>
            <b>Noisy phone line:</b> raise <i>Speech confidence</i> and <i>Minimum volume</i>, and set{' '}
            <i>Words needed to interrupt</i> to 3 (or turn barge-in off).
          </li>
          <li>
            <b>Bot talks over users who pause:</b> raise <i>End-of-turn timeout</i>.
          </li>
          <li>
            <b>Bot interrupts itself on speakers:</b> raise <i>Words needed to interrupt</i> to 2 or more, or turn
            barge-in off (echo can sound like the user).
          </li>
          <li>
            <b>Snappier replies:</b> lower <i>End-of-turn timeout</i> to about 1500.
          </li>
          <li>
            <b>Calls feel silent while the AI works:</b> turn on <i>Say a filler while thinking</i>, and{' '}
            <i>Say a phrase before tool calls</i> if the agent uses slow tools.
          </li>
        </ul>
      </div>
    </div>
  );
}

export default ConversationConfigGuide;
