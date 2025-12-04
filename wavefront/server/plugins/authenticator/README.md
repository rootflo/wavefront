# Authenticator Plugin

A unified authentication plugin system that supports multiple authentication methods including email/password, Google OAuth, and Microsoft OAuth.

## Features

- **Unified Authentication Interface**: Single API for all authentication methods
- **Multiple Authenticator Support**: Email/password, Google OAuth, Microsoft OAuth
- **Admin Controls**: Enable/disable authentication methods via admin API
- **Session Management**: Integrated with existing session system
- **Singleton Pattern**: Each authenticator type uses singleton pattern for efficiency
- **Configuration Validation**: Built-in validation for all authenticator configurations
- **Health Monitoring**: Health check endpoints for each authenticator

## Architecture

### Core Components

1. **AuthenticatorABC**: Abstract base class defining the interface for all authenticators
2. **AuthenticatorFactory**: Thread-safe singleton factory that manages authenticator instances with caching and lifecycle management
3. **SessionManager**: Handles session creation and management for all auth types
4. **Individual Authenticators**: Specific implementations for each auth method
5. **Controller Separation**: 
   - `authenticator_controller`: Manages individual authenticator instances
   - `allowed_authenticator_controller`: Manages system-wide authenticator type settings

### Supported Authenticator Types

- `email_password`: Traditional email and password authentication
- `google_oauth`: Google OAuth 2.0 authentication
- `microsoft_oauth`: Microsoft OAuth 2.0 authentication
- `saml`: SAML single sign-on (planned)
- `ldap`: LDAP directory authentication (planned)

## Configuration

### Email/Password Configuration

```json
{
    "password_policy": {
        "min_length": 8,
        "require_uppercase": true,
        "require_lowercase": true,
        "require_numbers": true,
        "require_special_chars": false,
        "max_attempts": 5,
        "lockout_duration": 900
    },
    "two_factor_enabled": false,
    "password_reset_enabled": true,
    "session_timeout": 3600,
    "rate_limit_enabled": true
}
```

### Google OAuth Configuration

```json
{
    "client_id": "your_google_client_id",
    "client_secret": "your_google_client_secret",
    "redirect_uri": "https://your-domain.com/auth/google/callback",
    "scopes": ["openid", "email", "profile"],
    "hosted_domain": null,
    "access_type": "offline",
    "prompt": "consent"
}
```

### Microsoft OAuth Configuration

```json
{
    "client_id": "your_microsoft_client_id",
    "client_secret": "your_microsoft_client_secret",
    "tenant_id": "your_tenant_id",
    "redirect_uri": "https://your-domain.com/auth/microsoft/callback",
    "scopes": ["openid", "email", "profile"],
    "authority": "https://login.microsoftonline.com/",
    "response_type": "code",
    "response_mode": "query"
}
```

## API Endpoints

### Authentication Endpoints

- `POST /v1/auth/authenticate` - Unified authentication endpoint
- `POST /v1/auth/oauth/init` - Initialize OAuth flow
- `GET /v1/auth/oauth/callback/google` - Google OAuth callback
- `GET /v1/auth/oauth/callback/microsoft` - Microsoft OAuth callback

### Admin Endpoints

#### Authenticator Instance Management
- `POST /v1/authenticators` - Create authenticator configuration
- `GET /v1/authenticators/{auth_name}` - Get authenticator configuration
- `PUT /v1/authenticators/{auth_name}` - Update authenticator configuration
- `DELETE /v1/authenticators/{auth_name}` - Delete authenticator configuration
- `GET /v1/authenticators/{auth_name}/health` - Check authenticator health

#### Allowed Authenticator Type Management
- `GET /v1/allowed-authenticators/types` - Get enabled authenticator types
- `POST /v1/allowed-authenticators/types/{auth_type}/enable` - Enable authenticator type
- `POST /v1/allowed-authenticators/types/{auth_type}/disable` - Disable authenticator type

## Usage Examples

### Email/Password Authentication

```json
POST /v1/auth/authenticate
{
    "auth_type": "email_password",
    "credentials": {
        "email": "user@example.com",
        "password": "securepassword"
    }
}
```

### Google OAuth Flow

1. Initialize OAuth flow:
```json
POST /v1/auth/oauth/init
{
    "auth_type": "google_oauth"
}
```

2. Redirect user to returned `authorization_url`

3. Handle callback automatically at `/v1/auth/oauth/callback/google`

### Microsoft OAuth Flow

1. Initialize OAuth flow:
```json
POST /v1/auth/oauth/init
{
    "auth_type": "microsoft_oauth"
}
```

2. Redirect user to returned `authorization_url`

3. Handle callback automatically at `/v1/auth/oauth/callback/microsoft`

## Database Setup

Run the setup script to initialize the database:

```sql
-- Run setup_authenticator_data.sql to populate initial data
```

This will create:
- Allowed authenticator types in `allowed_authenticator` table
- Default configurations in `authenticator` table

## Security Features

- **Rate Limiting**: Built-in rate limiting for email/password authentication
- **Password Policies**: Configurable password complexity requirements
- **Session Management**: Secure session creation and validation
- **Token Encryption**: OAuth tokens and secrets are stored securely
- **Domain Restrictions**: Google OAuth supports hosted domain restrictions

## Development

### Adding New Authenticators

1. Create new authenticator class extending `AuthenticatorABC`
2. Implement all required methods
3. Add configuration class
4. Update `AuthenticatorPlugin` factory to include new type
5. Add database entry to `allowed_authenticator` table

### Testing

Test endpoints using the health check APIs:

```bash
# Test authenticator health
GET /v1/authenticators/{auth_name}/health

# Test specific auth flow
POST /v1/auth/authenticate
```

## Dependencies

- `requests`: For OAuth API calls to Google and Microsoft endpoints

## Recent Improvements

### v0.1.0 Updates

- **Factory Deadlock Fix**: Resolved a critical deadlock issue in `AuthenticatorFactory.update_authenticator()` that was causing API freezes during authenticator updates
- **Controller Separation**: Split authenticator management into two separate controllers for better organization:
  - `authenticator_controller`: Manages individual authenticator instances
  - `allowed_authenticator_controller`: Manages system-wide authenticator type enablement
- **Dependency Cleanup**: Removed unnecessary dependencies and ensured all required packages are properly declared
- **Threading Improvements**: Enhanced thread safety in the factory pattern with better lock management

### Performance Enhancements

- **Caching**: Authenticator instances are cached to improve performance
- **Validation**: Configuration validation happens before instance creation to prevent unnecessary object creation
- **Error Handling**: Improved error handling with proper exception propagation

## Error Handling

All authenticators return standardized `AuthResult` objects with:
- `success`: Boolean indicating success/failure
- `user_info`: User information on success
- `access_token`/`refresh_token`: OAuth tokens when applicable
- `error`: Error message on failure
- `error_code`: Machine-readable error code