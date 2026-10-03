import { IndexStatus, KnowledgeBaseIndexStatusData } from '@app/api/knowledge-base-service';
import { Button } from '@app/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { cn } from '@app/lib/utils';
import dayjs from 'dayjs';
import React, { useState } from 'react';
import { INDEX_STATUS_STYLES } from './indexStatusStyles';

type CountKey = IndexStatus | 'NOT_TRACKED';

// Indexing timestamps come from the server in UTC without an offset
const parseUtc = (value: string) => dayjs(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);

interface IndexStatusSummaryProps {
  status: KnowledgeBaseIndexStatusData | null | undefined;
  loading: boolean;
}

/**
 * Document counts per indexing state for a knowledge base, refreshed by the
 * caller while anything is queued or indexing. Failed documents can be opened
 * to see why they failed.
 */
const IndexStatusSummary: React.FC<IndexStatusSummaryProps> = ({ status, loading }) => {
  const [showFailed, setShowFailed] = useState(false);

  if (loading && !status) {
    return <p className="frost-text-muted text-sm">Loading indexing status...</p>;
  }
  if (!status) {
    return null;
  }

  const { counts, total, failed_documents: failedDocuments } = status;
  const pending = counts.QUEUED + counts.IN_PROGRESS;
  const keys: CountKey[] = ['QUEUED', 'IN_PROGRESS', 'COMPLETE', 'FAILED'];
  if (counts.NOT_TRACKED > 0) {
    keys.push('NOT_TRACKED');
  }

  return (
    <div className="frost-control ring-frost-border flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border px-4 py-3 ring-1">
      <Stat label="Documents" value={total} />
      {keys.map((key) => {
        const style = INDEX_STATUS_STYLES[key];
        const stat = <Stat label={style.label} value={counts[key]} valueClassName={style.className} />;
        if (key === 'FAILED' && counts.FAILED > 0) {
          return (
            <button
              key={key}
              type="button"
              className="cursor-pointer rounded underline-offset-4 hover:underline"
              onClick={() => setShowFailed(true)}
              title="Show failed documents"
            >
              {stat}
            </button>
          );
        }
        return <React.Fragment key={key}>{stat}</React.Fragment>;
      })}
      {pending > 0 && <span className="frost-text-muted ml-auto text-xs">Updating every few seconds…</span>}

      <Dialog open={showFailed} onOpenChange={setShowFailed}>
        <DialogContent className="max-h-[80vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Failed documents</DialogTitle>
            <DialogDescription>
              {counts.FAILED} document{counts.FAILED === 1 ? '' : 's'} could not be indexed
              {counts.FAILED > failedDocuments.length ? `; showing the latest ${failedDocuments.length}` : ''}. Delete
              and upload again to retry.
            </DialogDescription>
          </DialogHeader>
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[35%]">Document</TableHead>
                <TableHead className="w-[45%]">Error</TableHead>
                <TableHead className="w-[20%]">Failed at</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {failedDocuments.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="max-w-0 truncate font-medium" title={doc.file_name}>
                    {doc.file_name}
                  </TableCell>
                  <TableCell className="text-sm break-words whitespace-normal">
                    {doc.index_error || 'No error recorded'}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {doc.index_status_updated_at ? parseUtc(doc.index_status_updated_at).format('DD MMM, HH:mm') : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setShowFailed(false)}>
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: number; valueClassName?: string }> = ({
  label,
  value,
  valueClassName,
}) => (
  <div className="flex flex-col items-start">
    <span className={cn('frost-text text-lg leading-tight font-semibold', valueClassName)}>{value}</span>
    <span className="frost-text-muted text-xs">{label}</span>
  </div>
);

export default IndexStatusSummary;
