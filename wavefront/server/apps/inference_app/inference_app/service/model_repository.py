from typing import Dict
import os
import torch
import io
from common_module.log.logger import logger
from flo_cloud.cloud_storage import CloudStorageManager


class ModelRepository:
    def __init__(
        self,
        cloud_storage_manager: CloudStorageManager,
    ):
        self.cloud_storage_manager = cloud_storage_manager
        self.model_storage_dir = os.getenv('MODEL_STORAGE_DIR', './models')
        os.makedirs(self.model_storage_dir, exist_ok=True)
        # Cache for loaded models - stores model instances in memory
        self._model_cache: Dict[str, torch.nn.Module] = {}

    def _is_model_cached_locally(
        self, model_name: str, file_path: str, expected_local_model_dir: str
    ) -> bool:
        """
        Checks if the model is available in the local persistent storage.
        """
        return os.path.exists(
            expected_local_model_dir
        ) and f'{model_name}.{file_path.split(".")[-1]}' in os.listdir(
            expected_local_model_dir
        )

    async def load_model(self, model_info: dict, bucket_name: str):
        model_id = model_info['model_id']
        expected_local_model_dir = self.model_storage_dir
        model_name = model_info['model_name']
        file_path = model_info['model_path']
        model_id = model_info['model_id']

        local_model_filename = os.path.join(
            expected_local_model_dir, f'{model_name}.{file_path.split(".")[1]}'
        )
        local_model_full_path = os.path.join(local_model_filename)

        if self._is_model_cached_locally(
            model_name, file_path, expected_local_model_dir
        ):
            logger.info(f'Model {model_id} found in local persistent storage, loading.')
            if model_id in self._model_cache:
                return self._model_cache[model_id]
            else:
                with open(local_model_full_path, 'rb') as f:
                    model_bytes_data = f.read()
                return torch.load(io.BytesIO(model_bytes_data), weights_only=False)
        else:
            logger.info(
                f'Model {model_id} not found in local persistent storage, loading from cloud storage.'
            )
            model_bytes_data = self.cloud_storage_manager.read_file(
                bucket_name, file_path
            )
            model = torch.load(io.BytesIO(model_bytes_data), weights_only=False)
            # Save to local persistent storage after fetching from cloud
            os.makedirs(os.path.dirname(local_model_full_path), exist_ok=True)
            with open(local_model_full_path, 'wb') as f:
                f.write(model_bytes_data)
            self._model_cache[model_id] = model
            logger.info(f'Model {model_id} loaded and cached in memory.')
        return model
