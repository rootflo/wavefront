import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Secret, hasSecretRef, secretRef } from '@app/types/secret';
import React from 'react';
import { Link } from 'react-router';

// Credentials live in the Secrets page; the service only holds `${secrets.NAME}`.
const WHOLE_REF = /^\$\{secrets\.([A-Z][A-Z0-9_]*)\}$/;

interface SecretInputProps {
  value: string;
  onChange: (value: string) => void;
  secrets: Secret[];
  disabled?: boolean;
  placeholder?: string;
}

/**
 * A secret field: pick a secret to insert its reference, or type a value.
 *
 * Typing a literal is still possible for deployments without encryption; it is
 * masked. A reference is not a credential, so it is shown as text.
 */
const SecretInput = React.forwardRef<HTMLInputElement, SecretInputProps>(
  ({ value, onChange, secrets, disabled, placeholder }, ref) => {
    const selected = WHOLE_REF.exec(value || '')?.[1];

    return (
      <div className="flex w-full flex-col gap-2 sm:flex-row">
        <Select value={selected ?? ''} onValueChange={(name) => onChange(secretRef(name))} disabled={disabled}>
          <SelectTrigger className="sm:w-56">
            <SelectValue placeholder="Use a secret" />
          </SelectTrigger>
          <SelectContent>
            {secrets.map((secret) => (
              <SelectItem key={secret.id} value={secret.name}>
                {secret.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          ref={ref}
          className="flex-1"
          type={hasSecretRef(value || '') ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? `${secretRef('NAME')} or a value`}
          disabled={disabled}
          autoComplete="new-password"
        />
      </div>
    );
  }
);
SecretInput.displayName = 'SecretInput';

/** Names of the secrets a field can reference, with a link to manage them. */
export const SecretNamesHint: React.FC<{ appId?: string; secrets: Secret[] }> = ({ appId, secrets }) => (
  <p className="frost-text-muted text-xs">
    {secrets.length > 0 ? (
      <>Available secrets: {secrets.map((secret) => secret.name).join(', ')}. </>
    ) : (
      <>No secrets yet. </>
    )}
    <Link className="text-brand hover:underline" to={`/apps/${appId}/secrets`}>
      Manage secrets
    </Link>
  </p>
);

export default SecretInput;
