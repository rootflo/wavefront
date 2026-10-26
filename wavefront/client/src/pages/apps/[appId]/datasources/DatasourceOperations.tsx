import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import React from 'react';
import { useDatasourceOperation } from './useDatasourceOperation';
import OperationPicker from './OperationPicker';
import OperationForm from './OperationForm';
import OperationResult from './OperationResult';

interface DatasourceOperationsProps {
  datasourceId: string;
}

/**
 * Bulk and advanced operations, as a guided flow: pick what to do, fill in the numbered steps, preview what an
 * update or delete will touch, then run it and see the result and the exact API request beside the form.
 */
const DatasourceOperations: React.FC<DatasourceOperationsProps> = ({ datasourceId }) => {
  const op = useDatasourceOperation(datasourceId);
  const { selectedOperation, running, confirmOpen, setConfirmOpen, table, filter, operation, execute } = op;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pb-6">
      {/* What to do */}
      <OperationPicker op={op} />

      <div className="grid min-h-0 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* How */}
        <OperationForm op={op} />

        {/* What happened */}
        <OperationResult op={op} />
      </div>

      {confirmOpen && (
        <DeleteConfirmationDialog
          isOpen={confirmOpen}
          title={operation.label}
          message={
            selectedOperation === 'delete-rows'
              ? `Delete every row in "${table}" where ${filter.trim()}? This cannot be undone.`
              : selectedOperation === 'update-rows'
                ? `Update every row in "${table}" where ${filter.trim()}? Their current values are overwritten.`
                : 'Update rows in every listed table? Their current values are overwritten, all in one transaction.'
          }
          onConfirm={() => void execute()}
          onCancel={() => setConfirmOpen(false)}
          loading={running}
          confirmLabel={selectedOperation === 'delete-rows' ? 'Delete' : 'Update'}
          cancelLabel="Cancel"
        />
      )}
    </div>
  );
};

export default DatasourceOperations;
