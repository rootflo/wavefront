import { ProblemsPanel, type Problem } from '@app/components/WorkflowBuilder/ProblemsPanel';
import ThemeToggle from '@app/components/ThemeToggle';
import { Button } from '@app/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React from 'react';
import LazyWorkflowVisualEditor from './LazyWorkflowVisualEditor';
import { WorkflowSaveAction } from './useWorkflowDraftSave';

interface WorkflowEditorWorkspaceProps {
  title: React.ReactNode;
  subtitle: React.ReactNode;
  yaml: string;
  onYamlChange: (yaml: string) => void;
  saving: boolean;
  submitAction: WorkflowSaveAction | null;
  validationErrors: Problem[];
  onDismissValidationErrors?: () => void;
  cancelLabel?: string;
  onCancel: () => void;
  // Edit mode: Save / Save as new version
  onSave?: (createNewVersion: boolean) => void;
  // Create mode: a single Create button
  onCreate?: () => void;
  // Tooltip for Save in edit mode, e.g. which version it overwrites
  saveHint?: string;
  // Extra inputs shown after the title: workflow ID and namespace when creating, the version selector when editing
  headerFields?: React.ReactNode;
}

// Full-screen workflow editor (command bar + Visual/YAML tabs) used by the standalone editor page for create and edit
const WorkflowEditorWorkspace: React.FC<WorkflowEditorWorkspaceProps> = ({
  title,
  subtitle,
  yaml,
  onYamlChange,
  saving,
  submitAction,
  validationErrors,
  onDismissValidationErrors,
  cancelLabel = 'Cancel',
  onCancel,
  onSave,
  onCreate,
  headerFields,
  saveHint,
}) => (
  <>
    <ProblemsPanel
      title={`${validationErrors.length} ${validationErrors.length === 1 ? 'problem prevents' : 'problems prevent'} saving`}
      problems={validationErrors}
      onDismiss={onDismissValidationErrors}
      className="absolute top-16 right-4 z-40"
    />
    <Tabs defaultValue="visual" className="flex h-full min-h-0 w-full flex-col">
      {/* TOP COMMAND BAR */}
      <div className="border-border bg-card/95 z-30 flex h-auto min-h-14 shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-2 backdrop-blur-md md:h-14 md:flex-nowrap md:gap-4 md:py-0">
        <div className="flex min-w-0 items-center gap-2 overflow-x-auto">
          <div className="bg-primary/10 text-primary flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold shadow-xs">
            WF
          </div>
          <div>
            {title}
            <span className="text-muted-foreground text-[10px]">{subtitle}</span>
          </div>
          {headerFields && (
            <>
              <div className="bg-border mx-1 h-4 w-[1px]" />
              {headerFields}
            </>
          )}
        </div>

        {/* Center: Tabs Switcher */}
        <TabsList className="bg-muted/60 h-8 shrink-0 p-0.5">
          <TabsTrigger value="visual" className="h-7 px-3 text-xs">
            Visual Builder
          </TabsTrigger>
          <TabsTrigger value="yaml" className="h-7 px-3 text-xs">
            YAML Code
          </TabsTrigger>
        </TabsList>

        {/* Right: Actions (never shrink, so Close / Save stay visible) */}
        <div className="flex shrink-0 items-center gap-2">
          <ThemeToggle />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground h-8 text-xs"
            onClick={onCancel}
            disabled={saving}
          >
            {cancelLabel}
          </Button>
          {onCreate && (
            <Button
              type="button"
              size="sm"
              className="h-8 text-xs shadow-xs"
              disabled={saving}
              loading={saving}
              onClick={onCreate}
            >
              Create Workflow
            </Button>
          )}
          {onSave && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                disabled={saving}
                loading={saving && submitAction === 'save'}
                title={saveHint}
                onClick={() => onSave(false)}
              >
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                className="h-8 text-xs shadow-xs"
                disabled={saving}
                loading={saving && submitAction === 'new'}
                title="Creates a new version from your edits. It is not promoted to current."
                onClick={() => onSave(true)}
              >
                Save as new version
              </Button>
            </>
          )}
        </div>
      </div>

      {/* TABS CONTENT: 100% REMAINING REAL ESTATE */}
      <TabsContent
        value="visual"
        forceMount
        className="m-0 h-[calc(100vh-56px)] min-h-0 w-full flex-1 overflow-hidden outline-none data-[state=inactive]:hidden"
      >
        <LazyWorkflowVisualEditor yamlContent={yaml} onChange={onYamlChange} />
      </TabsContent>

      <TabsContent
        value="yaml"
        className="m-0 flex h-[calc(100vh-56px)] min-h-0 w-full flex-1 flex-col gap-2 p-4 outline-none"
      >
        <CodeMirror
          value={yaml}
          editable={true}
          onChange={onYamlChange}
          theme="dark"
          height="100%"
          width="100%"
          maxWidth="100%"
          className="border-border w-full min-w-0 flex-1 overflow-auto rounded-xl border"
          extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
        />
        <p className="text-muted-foreground shrink-0 text-xs">Define your workflow configuration in YAML format.</p>
      </TabsContent>
    </Tabs>
  </>
);

export default WorkflowEditorWorkspace;
