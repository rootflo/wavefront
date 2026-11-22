import { ToolsDetailsData } from '@app/types/tool';
import yaml from 'js-yaml';

export type YamlAgentTool = {
  name?: string;
  name_override?: string;
  prefilled_params?: Record<string, string>;
  description_override?: string;
};

export type SelectedTool = { id: string; value: string };

export function mergeToolPrefilledValues(tool: ToolsDetailsData): Record<string, string> {
  return (tool.prefilled_values || []).reduce(
    (acc: Record<string, string>, obj: { [key: string]: string }) => ({
      ...acc,
      ...obj,
    }),
    {} as Record<string, string>
  );
}

export function matchYamlToolToDetails(
  yamlTool: string | YamlAgentTool,
  toolsDetails: ToolsDetailsData[]
): ToolsDetailsData | undefined {
  const normalized: YamlAgentTool = typeof yamlTool === 'string' ? { name: yamlTool } : yamlTool;
  const toolName = normalized.name;
  if (!toolName) return undefined;

  const candidates = toolsDetails.filter((tool) => tool.name === toolName);
  if (candidates.length === 0) return undefined;
  if (candidates.length === 1) return candidates[0];

  const yamlPrefill = normalized.prefilled_params || {};
  const exact = candidates.find(
    (tool) => JSON.stringify(mergeToolPrefilledValues(tool)) === JSON.stringify(yamlPrefill)
  );
  if (exact) return exact;

  const partial = candidates.find((tool) => {
    const pref = mergeToolPrefilledValues(tool);
    return Object.entries(yamlPrefill).every(([key, value]) => pref[key] === value);
  });
  return partial ?? candidates[0];
}

/** Rebuild the tools combobox selection from `agent.tools` in YAML. */
export function selectedToolsFromYaml(yamlContent: string, toolsDetails: ToolsDetailsData[]): SelectedTool[] {
  if (!yamlContent || toolsDetails.length === 0) return [];

  try {
    const parsed = yaml.load(yamlContent) as {
      agent?: { tools?: Array<string | YamlAgentTool> };
    } | null;
    const tools = parsed?.agent?.tools;
    if (!Array.isArray(tools)) return [];

    const selected: SelectedTool[] = [];
    for (const yamlTool of tools) {
      const match = matchYamlToolToDetails(yamlTool, toolsDetails);
      if (match) {
        selected.push({ id: match.display_name, value: match.display_name });
      }
    }
    return selected;
  } catch {
    return [];
  }
}

export function selectedToolsEqual(a: SelectedTool[], b: SelectedTool[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((tool, index) => tool.value === b[index]?.value);
}

export function buildYamlToolsFromSelection(
  selectedTools: SelectedTool[],
  toolsDetails: ToolsDetailsData[]
): YamlAgentTool[] {
  return toolsDetails
    .filter((tool) => selectedTools.some((selected) => selected.value === tool.display_name))
    .map((tool) => {
      const prefilledParams = mergeToolPrefilledValues(tool);
      return {
        name: tool.name,
        prefilled_params: Object.keys(prefilledParams).length > 0 ? prefilledParams : undefined,
        name_override: tool.name,
        description_override: tool.description,
      };
    });
}
