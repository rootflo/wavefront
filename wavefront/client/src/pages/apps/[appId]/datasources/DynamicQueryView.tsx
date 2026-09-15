import { Button } from '@app/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { DynamicQueryItem } from '@app/types/datasource';
import { removeUnderscoreAndSentenceCase } from '@app/utils/string-formatting';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import { useEffect, useState } from 'react';
import { buildDynamicQueryYaml } from './dynamic-query-utils';

const DynamicQueryView = ({
  queryItems,
  queryCrud,
  selectedQuery,
  queryName,
  handleDynamicQueryEdit,
  handleClose,
  handleDynamicQueryExecute,
  executeResult,
  setExecuteResult,
  executing,
}: {
  queryItems: DynamicQueryItem[];
  setQueryCrud: React.Dispatch<
    React.SetStateAction<{
      view: boolean;
      edit: boolean;
      create: boolean;
      delete: boolean;
      execute: boolean;
    }>
  >;
  setQueryItems: React.Dispatch<React.SetStateAction<DynamicQueryItem[]>>;
  setSelectedQuery: React.Dispatch<React.SetStateAction<string | null>>;
  queryCrud: {
    view: boolean;
    edit: boolean;
    create: boolean;
    delete: boolean;
    execute: boolean;
  };
  selectedQuery: string | null;
  queryName: string;
  handleDynamicQueryEdit: (queryContent: string) => void;
  handleClose: () => void;
  handleDynamicQueryExecute: (params: Record<string, string>) => void;
  executeResult: Record<string, unknown>[];
  setExecuteResult: React.Dispatch<React.SetStateAction<Record<string, unknown>[]>>;
  executing: boolean;
}) => {
  const [queryContent, setQueryContent] = useState('');
  const [queryParameters, setQueryParameters] = useState<Record<string, 'string' | 'number' | 'boolean' | 'date'>>({});
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const generateQueryParameters = () => {
    if (selectedQuery && queryItems.length > 0) {
      const allParameters: Record<string, 'string' | 'number' | 'boolean' | 'date'> = {};

      const uniqueParametersSet = new Set<string>();

      queryItems.forEach((query) => {
        const queryParametersList = query.parameters;
        if (queryParametersList && queryParametersList.length > 0) {
          queryParametersList.forEach(({ name, type }) => {
            if (!uniqueParametersSet.has(name)) {
              allParameters[name] = type as 'string' | 'number' | 'boolean' | 'date';
              uniqueParametersSet.add(name);
            }
          });
        }
      });

      setQueryParameters(allParameters);

      const initialValues: Record<string, string> = {};
      Object.keys(allParameters).forEach((key) => {
        initialValues[key] = '';
      });
      setParameterValues(initialValues);
      setFormErrors({});
    }
  };

  const handleParameterChange = (parameterName: string, value: string) => {
    setParameterValues((prev) => ({
      ...prev,
      [parameterName]: value,
    }));

    if (formErrors[parameterName]) {
      setFormErrors((prev) => ({
        ...prev,
        [parameterName]: '',
      }));
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    let isValid = true;

    Object.keys(queryParameters).forEach((parameterName) => {
      const value = parameterValues[parameterName]?.trim();
      const parameterType = queryParameters[parameterName];

      if (!value) {
        errors[parameterName] = 'This field is required';
        isValid = false;
      } else {
        switch (parameterType) {
          case 'number':
            if (isNaN(Number(value))) {
              errors[parameterName] = 'Must be a valid number';
              isValid = false;
            }
            break;
          case 'date':
            if (isNaN(Date.parse(value))) {
              errors[parameterName] = 'Must be a valid date (YYYY-MM-DD)';
              isValid = false;
            }
            break;
          case 'boolean':
            if (!['true', 'false', '1', '0'].includes(value.toLowerCase())) {
              errors[parameterName] = 'Must be true/false or 1/0';
              isValid = false;
            }
            break;
        }
      }
    });

    setFormErrors(errors);
    return isValid;
  };

  const handleExecuteQuery = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (validateForm()) {
      handleDynamicQueryExecute(parameterValues);
      setExecuteResult([]);
    }
  };

  useEffect(() => {
    setQueryContent(buildDynamicQueryYaml(selectedQuery, queryName, queryItems));
  }, [selectedQuery, queryName, queryItems]);

  useEffect(() => {
    generateQueryParameters();
  }, [queryItems]);

  const isOpen =
    (queryCrud.view || queryCrud.edit || queryCrud.execute) && (queryItems.length > 0 || queryCrud.execute);

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      handleClose();
    }
  };

  const getDialogTitle = () => {
    if (queryCrud.execute) return 'Execute Query';
    if (queryCrud.edit) return 'Edit Dynamic Query';
    return queryName;
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] w-full max-w-[calc(100%-2rem)] min-w-0 overflow-y-auto sm:max-w-[1100px]">
        <DialogHeader>
          <DialogTitle>{getDialogTitle()}</DialogTitle>
        </DialogHeader>
        {(queryCrud.view || queryCrud.edit) && (
          <div className="w-full min-w-0 rounded-xl border border-[#EFF0F1]">
            <CodeMirror
              className="w-full min-w-0 rounded-xl bg-white p-4 font-mono text-sm font-normal text-[#282828] outline-none"
              value={queryContent}
              height="400px"
              width="100%"
              maxWidth="100%"
              extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
              onChange={(value: string) => setQueryContent(value)}
              editable={queryCrud.edit}
              placeholder="Enter your dynamic query here..."
              theme="dark"
            />
          </div>
        )}
        {queryCrud.execute && (
          <div className="flex flex-col gap-6">
            <form
              onSubmit={(e) => {
                handleExecuteQuery(e);
              }}
              className="flex flex-col gap-6"
            >
              {queryParameters && Object.keys(queryParameters).length > 0 && (
                <div className="grid grid-cols-2 gap-6">
                  {Object.keys(queryParameters).map((parameter) => {
                    const parameterType = queryParameters[parameter];
                    const hasError = !!formErrors[parameter];

                    return (
                      <div key={parameter} className="flex flex-col gap-3">
                        <label className="text-base leading-normal font-normal text-[#282828]">
                          {removeUnderscoreAndSentenceCase(parameter)}
                          <span className="ml-1 text-red-500">*</span>
                          <span className="ml-2 text-sm text-[#878787]">({parameterType})</span>
                        </label>
                        <Input
                          type={parameterType === 'date' ? 'date' : parameterType === 'number' ? 'number' : 'text'}
                          value={parameterValues[parameter] || ''}
                          onChange={(e) => handleParameterChange(parameter, e.target.value)}
                          className={hasError ? 'border-red-500 focus:border-red-500' : ''}
                          placeholder={
                            parameterType === 'date'
                              ? 'YYYY-MM-DD'
                              : parameterType === 'boolean'
                                ? 'true/false'
                                : parameterType === 'number'
                                  ? 'Enter a number'
                                  : 'Enter value'
                          }
                        />
                        {hasError && <span className="text-sm text-red-500">{formErrors[parameter]}</span>}
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="flex flex-col gap-4">
                <h3 className="text-lg leading-4 font-medium text-black">Query Results</h3>
                <div className="max-h-[300px] overflow-auto rounded-xl border border-[#EFF0F1] bg-[#FBFBFB] p-4">
                  <pre className="text-sm font-normal whitespace-pre-wrap text-[#282828]">
                    {JSON.stringify(executeResult, null, 2)}
                  </pre>
                </div>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button type="submit" loading={executing}>
                  Execute Query
                </Button>
              </DialogFooter>
            </form>
          </div>
        )}

        {(queryCrud.edit || queryCrud.view) && (
          <DialogFooter>
            {queryCrud.edit && <Button onClick={() => handleDynamicQueryEdit(queryContent)}>Save</Button>}
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
};
export default DynamicQueryView;
