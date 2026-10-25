import { GetDatasourceResourceParams } from '@app/types/datasource';
import { Layers, List, ListPlus, PencilLine, Rows3, Trash2, Workflow } from 'lucide-react';
import React from 'react';

// The operations offered on a datasource, their request templates, and JSON helpers for their inputs

export type OperationId =
  | 'get-table-names'
  | 'get-table-data'
  | 'insert-rows'
  | 'update-rows'
  | 'delete-rows'
  | 'insert-multi'
  | 'update-multi';

interface Operation {
  id: OperationId;
  label: string;
  /** One line on the tile. */
  summary: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Changes or removes existing data, so it asks before running and its button is red. */
  destructive?: boolean;
  /** Works on one table picked in step 1. */
  needsTable?: boolean;
  /** Narrows to rows with a filter. */
  needsFilter?: 'optional' | 'required';
  /** Postgres only on the backend; other types answer "not implemented". */
  postgresOnly?: boolean;
  runLabel: string;
}

export const OPERATION_GROUPS: { title: string; hint: string; operations: Operation[] }[] = [
  {
    title: 'Read',
    hint: 'Look without changing anything',
    operations: [
      {
        id: 'get-table-names',
        label: 'List tables',
        summary: 'Every table in this datasource',
        icon: List,
        runLabel: 'List tables',
      },
      {
        id: 'get-table-data',
        label: 'Query rows',
        summary: 'Rows with chosen columns, filter, sort and grouping',
        icon: Rows3,
        needsTable: true,
        needsFilter: 'optional',
        runLabel: 'Run query',
      },
    ],
  },
  {
    title: 'Write',
    hint: 'Change one table',
    operations: [
      {
        id: 'insert-rows',
        label: 'Insert rows',
        summary: 'Add new rows to a table',
        icon: ListPlus,
        needsTable: true,
        runLabel: 'Insert',
      },
      {
        id: 'update-rows',
        label: 'Update rows',
        summary: 'Set new values on every row that matches',
        icon: PencilLine,
        needsTable: true,
        needsFilter: 'required',
        destructive: true,
        runLabel: 'Update rows',
      },
      {
        id: 'delete-rows',
        label: 'Delete rows',
        summary: 'Remove every row that matches',
        icon: Trash2,
        needsTable: true,
        needsFilter: 'required',
        destructive: true,
        runLabel: 'Delete rows',
      },
    ],
  },
  {
    title: 'Transactions',
    hint: 'Several tables, all or nothing',
    operations: [
      {
        id: 'insert-multi',
        label: 'Insert into several tables',
        summary: 'Related rows across tables in one go',
        icon: Layers,
        postgresOnly: true,
        runLabel: 'Insert',
      },
      {
        id: 'update-multi',
        label: 'Update several tables',
        summary: 'Related changes across tables in one go',
        icon: Workflow,
        postgresOnly: true,
        destructive: true,
        runLabel: 'Update',
      },
    ],
  },
];

export const OPERATIONS = OPERATION_GROUPS.flatMap((group) => group.operations);

export const INSERT_ROWS_TEMPLATE = `[
  { "name": "Asha", "email": "asha@example.com" },
  { "name": "Ravi", "email": "ravi@example.com" }
]`;

export const INSERT_MULTI_TEMPLATE = `[
  {
    "table_name": "orders",
    "data": [{ "order_id": "O-1", "amount": 120 }]
  },
  {
    "table_name": "order_items",
    "data": [{ "order_id": "O-1", "sku": "SKU-9", "qty": 2 }]
  }
]`;

export const UPDATE_MULTI_TEMPLATE = `[
  {
    "table_name": "orders",
    "filter": "order_id eq 'O-1'",
    "data": { "status": "shipped" }
  },
  {
    "table_name": "shipments",
    "filter": "order_id eq 'O-1'",
    "data": { "dispatched": true }
  }
]`;

// How many matching rows the preview fetches before an update or delete.
export const PREVIEW_LIMIT = 50;

export type Result =
  | { kind: 'tables'; names: string[] }
  // `params` is the read that produced the rows, repeated as-is to refresh them after an edit or delete.
  | {
      kind: 'rows';
      records: Record<string, unknown>[];
      title: string;
      note?: string;
      table: string;
      params: GetDatasourceResourceParams;
    }
  | { kind: 'message'; ok: boolean; text: string }
  | null;

export interface ApiRequest {
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  path: string;
  query?: Record<string, string | number | undefined>;
  body?: unknown;
}

export const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/** Parses the JSON editor's text, naming the problem instead of throwing. */
export const parseJson = (
  text: string
): { value: unknown; error?: undefined } | { value?: undefined; error: string } => {
  try {
    return { value: JSON.parse(text) };
  } catch (error) {
    return { error: `Invalid JSON: ${(error as Error).message}` };
  }
};
