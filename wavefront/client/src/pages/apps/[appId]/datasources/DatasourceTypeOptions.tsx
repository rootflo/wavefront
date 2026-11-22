import { SelectGroup, SelectItem, SelectLabel, SelectSeparator } from '@app/components/ui/select';
import React from 'react';
import { isFileStorageType } from './datasource-types';

/** The type dropdown's options in two groups, databases then file storage; an empty group is left out. */
const DatasourceTypeOptions = ({ types }: { types: { value: string; label: string }[] }) => {
  const groups = [
    { label: 'Databases', types: types.filter((type) => !isFileStorageType(type.value)) },
    { label: 'File storage', types: types.filter((type) => isFileStorageType(type.value)) },
  ].filter((group) => group.types.length > 0);

  return (
    <>
      {groups.map((group, index) => (
        <React.Fragment key={group.label}>
          {index > 0 ? <SelectSeparator /> : null}
          <SelectGroup>
            <SelectLabel className="frost-text-subtle text-[11px] font-semibold tracking-wider uppercase">
              {group.label}
            </SelectLabel>
            {group.types.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                {type.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </React.Fragment>
      ))}
    </>
  );
};

export default DatasourceTypeOptions;
