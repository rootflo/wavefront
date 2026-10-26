import floConsoleService from '@app/api';
import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { useCallback, useState } from 'react';
import { PickedFile, toBatches } from './dropped-files';
import { QueuedUpload } from './file-storage';

/** Files picked for upload into a file storage datasource, and uploading them in batches. */
export const useUploadQueue = (datasourceId: string) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [uploadQueue, setUploadQueue] = useState<QueuedUpload[]>([]);
  const [uploading, setUploading] = useState(false);

  /** Adds files to the upload list, replacing any still-pending one with the same path. */
  const queueFiles = useCallback((picked: PickedFile[]) => {
    if (picked.length === 0) return;
    const paths = new Set(picked.map((item) => item.relativePath));
    setUploadQueue((queue) => [
      ...queue.filter((item) => item.status !== 'pending' || !paths.has(item.relativePath)),
      ...picked.map((item) => ({ ...item, status: 'pending' as const })),
    ]);
  }, []);
  const clear = useCallback(() => setUploadQueue([]), []);

  /**
   * Uploads everything not yet done into `target`, keeping each file's sub-folder path. Files go in
   * batches (50 files or 25 MB per request); each file is marked done or failed from its batch's results.
   */
  const upload = async (target: string) => {
    const todo = uploadQueue.map((item, index) => ({ ...item, index })).filter((item) => item.status !== 'done');
    const setStatus = (indexes: number[], patch: (index: number) => Partial<QueuedUpload>) => {
      const wanted = new Set(indexes);
      setUploadQueue((queue) => queue.map((entry, i) => (wanted.has(i) ? { ...entry, ...patch(i) } : entry)));
    };

    setUploading(true);
    let uploaded = 0;
    let failed = 0;
    for (const batch of toBatches(todo)) {
      const indexes = batch.map((item) => item.index);
      setStatus(indexes, () => ({ status: 'uploading', error: undefined }));
      try {
        const response = await floConsoleService.datasourcesService.uploadFilesBatch(
          datasourceId,
          batch.map((item) => ({ file: item.file, path: `${target}${item.relativePath}` }))
        );
        const results = response.data?.data?.results ?? [];
        const errors = new Map(results.filter((r) => r.error).map((r) => [indexes[r.index], r.error!]));
        setStatus(indexes, (index) =>
          errors.has(index) ? { status: 'failed', error: errors.get(index) } : { status: 'done' }
        );
        failed += errors.size;
        uploaded += batch.length - errors.size;
      } catch (error) {
        const message = extractErrorMessage(error) || 'Upload failed';
        setStatus(indexes, () => ({ status: 'failed', error: message }));
        failed += batch.length;
      }
    }
    setUploading(false);

    if (uploaded > 0) notifySuccess(`Uploaded ${uploaded} file${uploaded === 1 ? '' : 's'}`);
    if (failed > 0) notifyError(`${failed} file${failed === 1 ? '' : 's'} failed to upload`);
    return { uploaded, failed };
  };

  return {
    uploadQueue,
    uploading,
    queueFiles,
    upload,
    clear,
    remove: (index: number) => setUploadQueue((queue) => queue.filter((_, i) => i !== index)),
    clearFinished: () => setUploadQueue((queue) => queue.filter((item) => item.status === 'done')),
  };
};
