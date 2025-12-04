from common_module.log.logger import logger
from api_services_module.core.router import ProxyRouter
import json
from api_services_module.utils.api_change_publisher import UpdateMessage


class ApiChangeProcessor:
    def __init__(self, proxy_router: ProxyRouter):
        self.proxy_router = proxy_router

    async def process_message(self, message: str):
        logger.debug(f'Processing message: {message}')
        try:
            update_message = UpdateMessage(**json.loads(message))

            if update_message.operation in ['update', 'create']:
                logger.info(f'Reloading service: {update_message.service_id}')
                await self.proxy_router.proxy.reload_service(
                    service_id=update_message.service_id
                )
                self.proxy_router.reload_service_routes(
                    service_id=update_message.service_id
                )

            elif update_message.operation == 'delete':
                logger.info(f'Removing service: {update_message.service_id}')
                self.proxy_router.proxy.remove_service(
                    service_id=update_message.service_id
                )
                self.proxy_router.remove_service_routes(
                    service_id=update_message.service_id
                )

            else:
                logger.error(f'Invalid operation: {update_message.operation}')

        except Exception as e:
            logger.error(f'Error processing message: {e}')
