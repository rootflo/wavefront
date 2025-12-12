import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import yaml from "js-yaml";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const validateDynamicQueryYaml = (yaml_str: string) => {
  try {
    const data = yaml.load(yaml_str) as Record<string, any>;
    // top require keys
    const requiredTop = ["id", "name", "queries"];

    for (const field of requiredTop) {
      if (!(field in data)) {
        return { valid: false, error: `Missing top-level field: ${field}` };
      }
    }
    // ✅ queries must be a list
    if (!Array.isArray(data.queries)) {
      return { valid: false, error: "queries must be a list" };
    }
    // each query must constain id,description,query
    for (let i = 0; i < data.queries.length; i++) {
      const q = data.queries[i];
      for (const field of ["id", "description", "query"]) {
        if (!(field in q)) {
          return {
            valid: false,
            error: `Missing field ${field} in query ${i + 1}`,
          };
        }
      }
      if ("parameters" in q) {
        if (typeof q.parameters !== "object") {
          return {
            valid: false,
            error: "parameters must be an object or array",
          };
        }
        const allowed = ["string", "number", "boolean", "date"];

        // Handle array format: [{ name: 'param1', type: 'date' }, ...]
        if (Array.isArray(q.parameters)) {
          for (let j = 0; j < q.parameters.length; j++) {
            const param = q.parameters[j];
            if (typeof param !== "object" || param === null) {
              return {
                valid: false,
                error: `Parameter ${j + 1} in query ${i + 1} must be an object`,
              };
            }
            if (!("name" in param)) {
              return {
                valid: false,
                error: `Missing 'name' field in parameter ${j + 1} of query ${
                  i + 1
                }`,
              };
            }
            if (!("type" in param)) {
              return {
                valid: false,
                error: `Missing 'type' field in parameter ${j + 1} of query ${
                  i + 1
                }`,
              };
            }
            if (typeof param.name !== "string") {
              return {
                valid: false,
                error: `Parameter name must be a string in parameter ${
                  j + 1
                } of query ${i + 1}`,
              };
            }
            if (!allowed.includes(param.type)) {
              return {
                valid: false,
                error: `Invalid parameter type '${param.type}' in parameter '${
                  param.name
                }' of query ${i + 1}. Allowed types: ${allowed.join(", ")}`,
              };
            }
          }
        }
      }
    }
    return { valid: true, error: "" };
  } catch (err) {
    return { valid: false, error: "Invalid YAML format" };
  }
};
