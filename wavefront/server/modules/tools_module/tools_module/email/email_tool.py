from db_repo_module.db_repo_container import DatabaseModuleContainer
from user_management_module.user_container import UserContainer


async def send_email(email_id: str, email_subject: str, email_body: str):
    # setting up the containers
    db_repo_container = DatabaseModuleContainer()
    user_module_container = UserContainer(
        db_client=db_repo_container.db_client,
        cache_manager=db_repo_container.cache_manager,
    )

    # setting up the emial part
    email_response = user_module_container.email_service().send_email(
        subject=email_subject, body=email_body, email_id=email_id
    )
    if email_response:
        return 'A password reset link has been sent to your registered email address.'

    else:
        return 'An error occurred while sending the email. Please verify your email address and try again later.'
