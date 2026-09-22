from typing import Optional, Tuple

from common_module.log.logger import logger
from google.cloud import recaptchaenterprise_v1
from google.cloud.recaptchaenterprise_v1 import Assessment

# Must match the action names used by the client when executing reCAPTCHA.
RECAPTCHA_ACTION_LOGIN = 'login'
RECAPTCHA_ACTION_SEND_RESET_PASSWORD = 'password_reset'
RECAPTCHA_ACTION_RESET_PASSWORD = 'reset_password'


class RecaptchaService:
    """Validates reCAPTCHA Enterprise tokens for login and similar UI actions."""

    DEFAULT_SCORE_THRESHOLD = 0.5

    def __init__(
        self,
        enabled=False,
        project_id: Optional[str] = None,
        site_key: Optional[str] = None,
        score_threshold=None,
    ):
        self.enabled = self._as_bool(enabled)
        self.project_id = (project_id or '').strip() or None
        self.site_key = (site_key or '').strip() or None
        self.score_threshold = self._as_float(
            score_threshold, self.DEFAULT_SCORE_THRESHOLD
        )

    @staticmethod
    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

    @staticmethod
    def _as_float(value, default: float) -> float:
        try:
            return float(value) if value is not None and value != '' else default
        except (TypeError, ValueError):
            return default

    def verify(self, token: Optional[str], action: str) -> Tuple[bool, Optional[str]]:
        """
        Verify a reCAPTCHA token for the given action.

        Returns (is_valid, error_message). When disabled, always returns (True, None).
        """
        if not self.enabled:
            return True, None

        if not self.project_id or not self.site_key:
            logger.error(
                'reCAPTCHA is enabled but project_id or site_key is not configured'
            )
            return False, 'reCAPTCHA verification is unavailable'

        if not token or not str(token).strip():
            return False, 'reCAPTCHA token is required'

        expected_action = (action or '').strip()
        if not expected_action:
            logger.error('reCAPTCHA verify called without an expected action')
            return False, 'reCAPTCHA verification failed'

        try:
            assessment = self.create_assessment(
                project_id=self.project_id,
                recaptcha_key=self.site_key,
                token=str(token).strip(),
                recaptcha_action=expected_action,
            )
        except Exception:
            logger.error('reCAPTCHA CreateAssessment call failed')
            return False, 'reCAPTCHA verification failed'

        if assessment is None:
            return False, 'reCAPTCHA verification failed'

        score = assessment.risk_analysis.score
        logger.info(
            f'reCAPTCHA assessment score={score} action={assessment.token_properties.action}'
        )
        if score < self.score_threshold:
            logger.warning(
                f'reCAPTCHA score {score} below threshold {self.score_threshold}'
            )
            return False, 'reCAPTCHA verification failed'

        return True, None

    def create_assessment(
        self,
        project_id: str,
        recaptcha_key: str,
        token: str,
        recaptcha_action: str,
    ) -> Optional[Assessment]:
        """Create an assessment to analyze the risk of a UI action."""
        client = recaptchaenterprise_v1.RecaptchaEnterpriseServiceClient()

        event = recaptchaenterprise_v1.Event()
        event.site_key = recaptcha_key
        event.token = token

        assessment = recaptchaenterprise_v1.Assessment()
        assessment.event = event

        request = recaptchaenterprise_v1.CreateAssessmentRequest()
        request.assessment = assessment
        request.parent = f'projects/{project_id}'

        response = client.create_assessment(request)

        if not response.token_properties.valid:
            logger.warning(
                'reCAPTCHA token invalid: '
                f'{response.token_properties.invalid_reason}'
            )
            return None

        if response.token_properties.action != recaptcha_action:
            logger.warning(
                'reCAPTCHA action mismatch: '
                f'expected={recaptcha_action} '
                f'got={response.token_properties.action}'
            )
            return None

        return response
