import { Button } from "@app/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@app/components/ui/dialog";
import { Input } from "@app/components/ui/input";
import { YamlReadData } from "@app/types/datasource";
import { removeUnderscoreAndSentenceCase } from "@app/utils/string-formatting";
import { langs } from "@uiw/codemirror-extensions-langs";
import CodeMirror from "@uiw/react-codemirror";
import { useEffect, useState } from "react";

const YamlView = ({
  yamlQueries,
  yamlCrud,
  selectedYaml,
  yamlName,
  handleYamlEdit,
  handleClose,
  handleYamlExecute,
  yamlExecuteResult,
  setYamlExecuteResult,
  executing,
}: {
  yamlQueries: YamlReadData[];
  setYamlCrud: React.Dispatch<
    React.SetStateAction<{
      view: boolean;
      edit: boolean;
      create: boolean;
      delete: boolean;
      execute: boolean;
    }>
  >;
  setYamlQueries: React.Dispatch<React.SetStateAction<YamlReadData[]>>;
  setSelectedYaml: React.Dispatch<React.SetStateAction<string | null>>;
  yamlCrud: {
    view: boolean;
    edit: boolean;
    create: boolean;
    delete: boolean;
    execute: boolean;
  };
  selectedYaml: string | null;
  yamlName: string;
  handleYamlEdit: (yamlContent: string) => void;
  handleClose: () => void;
  handleYamlExecute: (params: Record<string, string>) => void;
  yamlExecuteResult: Record<string, any>[];
  setYamlExecuteResult: React.Dispatch<
    React.SetStateAction<Record<string, any>[]>
  >;
  executing: boolean;
}) => {
  const [yamlContent, setYamlContent] = useState("");
  const [yamlParameters, setYamlParameters] = useState<
    Record<string, "string" | "number" | "boolean" | "date">
  >({});
  const [parameterValues, setParameterValues] = useState<
    Record<string, string>
  >({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const generateYamlParameters = () => {
    if (selectedYaml && yamlQueries.length > 0) {
      const allParameters: Record<
        string,
        "string" | "number" | "boolean" | "date"
      > = {};

      // Get unique parameters from all queries (since they might share parameters)
      const uniqueParametersSet = new Set<string>();

      yamlQueries.forEach((query) => {
        const queryParameters = query.parameters;
        if (queryParameters && queryParameters.length > 0) {
          queryParameters.forEach(({ name, type }) => {
            if (!uniqueParametersSet.has(name)) {
              allParameters[name] = type as
                | "string"
                | "number"
                | "boolean"
                | "date";
              uniqueParametersSet.add(name);
            }
          });
        }
      });

      setYamlParameters(allParameters);

      // Initialize parameter values with empty strings
      const initialValues: Record<string, string> = {};
      Object.keys(allParameters).forEach((key) => {
        initialValues[key] = "";
      });
      setParameterValues(initialValues);
      setFormErrors({});
    }
  };

  // Handle parameter input changes
  const handleParameterChange = (parameterName: string, value: string) => {
    setParameterValues((prev) => ({
      ...prev,
      [parameterName]: value,
    }));

    // Clear error when user starts typing
    if (formErrors[parameterName]) {
      setFormErrors((prev) => ({
        ...prev,
        [parameterName]: "",
      }));
    }
  };

  // Validate form
  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    let isValid = true;

    Object.keys(yamlParameters).forEach((parameterName) => {
      const value = parameterValues[parameterName]?.trim();
      const parameterType = yamlParameters[parameterName];

      if (!value) {
        errors[parameterName] = "This field is required";
        isValid = false;
      } else {
        // Type-specific validation
        switch (parameterType) {
          case "number":
            if (isNaN(Number(value))) {
              errors[parameterName] = "Must be a valid number";
              isValid = false;
            }
            break;
          case "date":
            if (isNaN(Date.parse(value))) {
              errors[parameterName] = "Must be a valid date (YYYY-MM-DD)";
              isValid = false;
            }
            break;
          case "boolean":
            if (!["true", "false", "1", "0"].includes(value.toLowerCase())) {
              errors[parameterName] = "Must be true/false or 1/0";
              isValid = false;
            }
            break;
        }
      }
    });

    setFormErrors(errors);
    return isValid;
  };

  // Handle form submission
  const handleExecuteQuery = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (validateForm()) {
      handleYamlExecute(parameterValues);
      setYamlExecuteResult([]);
    }
  };

  // Function to generate YAML string from current state
  const generateYamlString = () => {
    if (selectedYaml && yamlQueries.length > 0) {
      const queryId = selectedYaml.split(".")[0];
      return (
        `id: ${queryId}\n` +
        `name: ${yamlName}\n` +
        `queries:\n` +
        yamlQueries
          .map((query) => {
            const queryBlock =
              `  - id: ${query.id}\n` +
              `    query: |\n` +
              query.query
                .split("\n")
                .map((line) => `      ${line}`) // indent each line by 6 spaces
                .join("\n") +
              `\n` +
              `    description: ${query.description}\n` +
              (query.parameters && query.parameters.length > 0
                ? `    parameters:\n` +
                  query.parameters
                    .map(
                      (param) =>
                        `      - name: ${param.name}\n        type: ${param.type}`
                    )
                    .join("\n")
                : "");

            return queryBlock;
          })
          .join("\n")
      );
    }
    return "";
  };

  // Initialize and update YAML content when dependencies change
  useEffect(() => {
    setYamlContent(generateYamlString());
  }, [selectedYaml, yamlName, yamlQueries]);

  useEffect(() => {
    generateYamlParameters();
  }, [yamlQueries]);

  const isOpen =
    (yamlCrud.view || yamlCrud.edit || yamlCrud.execute) &&
    (yamlQueries.length > 0 || yamlCrud.execute);

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      handleClose();
    }
  };

  const getDialogTitle = () => {
    if (yamlCrud.execute) return "Execute Query";
    if (yamlCrud.edit) return "Edit YAML Query";
    return "View YAML Query";
  };

  const getDialogDescription = () => {
    if (yamlCrud.execute) return "Enter parameters to execute the query";
    if (yamlCrud.edit) return "Edit the YAML query configuration";
    return "View the YAML query configuration";
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] w-full max-w-[800px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{getDialogTitle()}</DialogTitle>
          <DialogDescription>{getDialogDescription()}</DialogDescription>
        </DialogHeader>
        {(yamlCrud.view || yamlCrud.edit) && (
          <div className="flex max-h-[700px] w-full flex-col gap-4 overflow-y-auto">
            <div className="rounded-xl border border-[#EFF0F1] bg-[#FBFBFB] p-4">
              <div className="mb-3 text-base font-normal leading-normal text-[#282828]">
                YAML Content:
              </div>
              <CodeMirror
                className="w-full max-w-max overflow-hidden rounded-xl border border-[#EFF0F1] bg-white p-4 font-mono text-sm font-normal text-[#282828] outline-none"
                value={yamlContent}
                height="400px"
                extensions={[langs.yaml()]}
                onChange={(value: string) => setYamlContent(value)}
                editable={yamlCrud.edit}
                placeholder="Enter your YAML content here..."
                theme="dark"
              />
              <p className="mt-3 text-sm font-normal leading-normal text-[#878787]">
                Define your YAML query configuration. Edit the content to modify
                query parameters and structure.
              </p>
            </div>
          </div>
        )}
        {yamlCrud.execute && (
          <div className="flex flex-col gap-6">
            <form
              onSubmit={(e) => {
                handleExecuteQuery(e);
              }}
              className="flex flex-col gap-6"
            >
              {yamlParameters && Object.keys(yamlParameters).length > 0 && (
                <div className="grid grid-cols-2 gap-6">
                  {Object.keys(yamlParameters).map((parameter) => {
                    const parameterType = yamlParameters[parameter];
                    const hasError = !!formErrors[parameter];

                    return (
                      <div key={parameter} className="flex flex-col gap-3">
                        <label className="text-base font-normal leading-normal text-[#282828]">
                          {removeUnderscoreAndSentenceCase(parameter)}
                          <span className="ml-1 text-red-500">*</span>
                          <span className="ml-2 text-sm text-[#878787]">
                            ({parameterType})
                          </span>
                        </label>
                        <Input
                          type={
                            parameterType === "date"
                              ? "date"
                              : parameterType === "number"
                              ? "number"
                              : "text"
                          }
                          value={parameterValues[parameter] || ""}
                          onChange={(e) =>
                            handleParameterChange(parameter, e.target.value)
                          }
                          className={
                            hasError
                              ? "border-red-500 focus:border-red-500"
                              : ""
                          }
                          placeholder={
                            parameterType === "date"
                              ? "YYYY-MM-DD"
                              : parameterType === "boolean"
                              ? "true/false"
                              : parameterType === "number"
                              ? "Enter a number"
                              : "Enter value"
                          }
                        />
                        {hasError && (
                          <span className="text-sm text-red-500">
                            {formErrors[parameter]}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="flex flex-col gap-4">
                <h3 className="text-lg font-medium leading-4 text-black">
                  Query Results
                </h3>
                <div className="max-h-[300px] overflow-auto rounded-xl border border-[#EFF0F1] bg-[#FBFBFB] p-4">
                  <pre className="whitespace-pre-wrap text-sm font-normal text-[#282828]">
                    {JSON.stringify(yamlExecuteResult, null, 2)}
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

        {(yamlCrud.edit || yamlCrud.view) && (
          <DialogFooter>
            {yamlCrud.edit && (
              <Button onClick={() => handleYamlEdit(yamlContent)}>Save</Button>
            )}
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
};
export default YamlView;
