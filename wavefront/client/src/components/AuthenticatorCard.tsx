import { AUTHENTICATOR_PROVIDERS_CONFIG, getProviderBadge } from '@app/config/authenticators';
import { Authenticator } from '@app/types/authenticator';
import clsx from 'clsx';
import React from 'react';
import ResourceCard, { ResourceCardMetadata } from './ResourceCard';

interface AuthenticatorCardProps {
  authenticator: Authenticator;
  onClick: (authId: string) => void;
  onDeleteClick: (e: React.MouseEvent, authenticator: Authenticator) => void;
}

const AuthenticatorCard: React.FC<AuthenticatorCardProps> = ({ authenticator, onClick, onDeleteClick }) => {
  const badge = getProviderBadge(authenticator.auth_type);
  const providerConfig = AUTHENTICATOR_PROVIDERS_CONFIG[authenticator.auth_type];

  const metadata: ResourceCardMetadata[] = [
    {
      label: 'Type',
      value: providerConfig?.name || authenticator.auth_type,
      className: clsx(badge.bg, badge.text, 'ring-1 ring-white/40'),
    },
    {
      label: 'Status',
      value: authenticator.is_enabled ? 'Enabled' : 'Disabled',
      className: authenticator.is_enabled
        ? 'bg-emerald-400/15 text-emerald-800 ring-1 ring-emerald-400/20'
        : 'bg-frost-glass-strong text-frost-text-subtle ring-1 ring-frost-border',
    },
  ];

  return (
    <ResourceCard
      title={authenticator.auth_name}
      description={authenticator.auth_desc || undefined}
      metadata={metadata}
      onClick={() => onClick(authenticator.auth_id)}
      onDeleteClick={(e) => onDeleteClick(e, authenticator)}
      deleteTitle="Delete authenticator"
    />
  );
};

export default AuthenticatorCard;
