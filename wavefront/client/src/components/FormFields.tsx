import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import { cn } from '@app/lib/utils';
import { ComponentProps, ReactNode } from 'react';
import { Control, FieldPathByValue, FieldValues } from 'react-hook-form';

// Labelled react-hook-form fields for any form: the shadcn Form primitives wired to an input, a
// textarea or a select, each showing its validation message. Pass the form's `control`; `name` is
// type-checked against the form values and must hold a string.

interface BaseFieldProps<TValues extends FieldValues, TName extends FieldPathByValue<TValues, string>> {
  control: Control<TValues>;
  name: TName;
  label: ReactNode;
  description?: ReactNode;
  /** Classes for the wrapping FormItem. */
  className?: string;
  labelClassName?: string;
}

type FormInputFieldProps<TValues extends FieldValues, TName extends FieldPathByValue<TValues, string>> = BaseFieldProps<
  TValues,
  TName
> &
  Omit<ComponentProps<typeof Input>, 'name' | 'value' | 'onChange' | 'onBlur'>;

export const FormInputField = <TValues extends FieldValues, TName extends FieldPathByValue<TValues, string>>({
  control,
  name,
  label,
  description,
  className,
  labelClassName,
  ...inputProps
}: FormInputFieldProps<TValues, TName>) => (
  <FormField
    control={control}
    name={name}
    render={({ field }) => (
      <FormItem className={className}>
        <FormLabel className={labelClassName}>{label}</FormLabel>
        <FormControl>
          <Input {...inputProps} {...field} />
        </FormControl>
        {description ? <FormDescription>{description}</FormDescription> : null}
        <FormMessage />
      </FormItem>
    )}
  />
);

type FormTextareaFieldProps<
  TValues extends FieldValues,
  TName extends FieldPathByValue<TValues, string>,
> = BaseFieldProps<TValues, TName> & Omit<ComponentProps<typeof Textarea>, 'name' | 'value' | 'onChange' | 'onBlur'>;

export const FormTextareaField = <TValues extends FieldValues, TName extends FieldPathByValue<TValues, string>>({
  control,
  name,
  label,
  description,
  className,
  labelClassName,
  ...textareaProps
}: FormTextareaFieldProps<TValues, TName>) => (
  <FormField
    control={control}
    name={name}
    render={({ field }) => (
      <FormItem className={className}>
        <FormLabel className={labelClassName}>{label}</FormLabel>
        <FormControl>
          <Textarea {...textareaProps} {...field} />
        </FormControl>
        {description ? <FormDescription>{description}</FormDescription> : null}
        <FormMessage />
      </FormItem>
    )}
  />
);

export interface FormSelectOption {
  value: string;
  label: ReactNode;
}

type FormSelectFieldProps<
  TValues extends FieldValues,
  TName extends FieldPathByValue<TValues, string>,
> = BaseFieldProps<TValues, TName> & {
  options: FormSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  /**
   * A first option that stands for the empty string (Radix Select cannot have an empty item), e.g.
   * "Inherit". Choosing it sets the field to ''.
   */
  emptyOption?: { value: string; label: ReactNode };
  /** Runs after the field changes, with the value written to the form. */
  onValueChange?: (value: string) => void;
  triggerClassName?: string;
};

export const FormSelectField = <TValues extends FieldValues, TName extends FieldPathByValue<TValues, string>>({
  control,
  name,
  label,
  description,
  className,
  labelClassName,
  options,
  placeholder,
  disabled,
  emptyOption,
  onValueChange,
  triggerClassName,
}: FormSelectFieldProps<TValues, TName>) => (
  <FormField
    control={control}
    name={name}
    render={({ field }) => (
      <FormItem className={className}>
        <FormLabel className={labelClassName}>{label}</FormLabel>
        <Select
          value={field.value || emptyOption?.value || undefined}
          onValueChange={(value) => {
            const next = emptyOption && value === emptyOption.value ? '' : value;
            field.onChange(next);
            onValueChange?.(next);
          }}
          disabled={disabled}
        >
          <FormControl>
            <SelectTrigger className={cn('w-full', triggerClassName)} onBlur={field.onBlur}>
              <SelectValue placeholder={placeholder} />
            </SelectTrigger>
          </FormControl>
          <SelectContent>
            {emptyOption ? <SelectItem value={emptyOption.value}>{emptyOption.label}</SelectItem> : null}
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {description ? <FormDescription>{description}</FormDescription> : null}
        <FormMessage />
      </FormItem>
    )}
  />
);
