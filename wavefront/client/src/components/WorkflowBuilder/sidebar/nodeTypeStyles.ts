import { NODE_TYPES } from '@app/constants/workflow-builder';
import { Bot, GitBranch, Cpu, ArrowRight, Layers, LucideIcon } from 'lucide-react';

export interface NodeTypeStyle {
  icon: LucideIcon;
  iconColor: string;
  activeBg: string;
}

export const DEFAULT_NODE_TYPE_STYLE: NodeTypeStyle = {
  icon: Bot,
  iconColor: 'text-emerald-500',
  activeBg: 'border-emerald-500 bg-emerald-500/10',
};

export const NODE_TYPE_STYLES: Record<string, NodeTypeStyle> = {
  [NODE_TYPES.AGENT]: DEFAULT_NODE_TYPE_STYLE,
  [NODE_TYPES.ROUTER]: {
    icon: GitBranch,
    iconColor: 'text-orange-500',
    activeBg: 'border-orange-500 bg-orange-500/10',
  },
  [NODE_TYPES.FUNCTION]: {
    icon: Cpu,
    iconColor: 'text-blue-500',
    activeBg: 'border-blue-500 bg-blue-500/10',
  },
  [NODE_TYPES.ITERATOR]: {
    icon: ArrowRight,
    iconColor: 'text-indigo-500',
    activeBg: 'border-indigo-500 bg-indigo-500/10',
  },
  [NODE_TYPES.SUBWORKFLOW]: {
    icon: Layers,
    iconColor: 'text-teal-500',
    activeBg: 'border-teal-500 bg-teal-500/10',
  },
};

export const getNodeTypeStyle = (nodeType?: string): NodeTypeStyle =>
  (nodeType && NODE_TYPE_STYLES[nodeType]) || DEFAULT_NODE_TYPE_STYLE;
