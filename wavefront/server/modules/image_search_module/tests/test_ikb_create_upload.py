# import asyncio
# import sys
# import base64
# from pathlib import Path
# import pytest


# from image_search_module.services.ikb_service import IKBService
# from image_search_module.services.image_matching_service import ImageMatchingService
# from image_search_module.services.reference_image_service import ReferenceImageService
# from image_search_module.services.algorithm_service import AlgorithmService
# from image_search_module.services.algorithm_factory import AlgorithmFactory
# from image_search_module.repositories.sift_features_repository import (
#     SIFTFeaturesRepository,
# )
# from image_search_module.repositories.ikb_repository import IKBRepository
# from image_search_module.algorithms.base import AlgorithmType

# # from .db_setup import setup_test_database
# from image_search_module.models.ikb_models import (
#     CreateIKBRequest,
#     IKBImageAddRequest,
#     IKBType,
#     IKBStatus,
# )
# from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
# from db_repo_module.models.image_search_models import (
#     ReferenceImageFeatures,
#     SIFTFeatures,
# )
# from db_repo_module.models.ikb_models import ImageKnowledgeBase

# import logging


# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# class MockCloudStorage:
#     """Mock cloud storage for testing"""

#     def __init__(self):
#         self.files = {}

#     async def save_file(self, file_path: str, file_data: bytes) -> str:
#         """Save file and return URL"""
#         self.files[file_path] = file_data
#         return f'mock://storage/{file_path}'

#     async def save_small_file(
#         self, file_content: bytes, bucket_name: str, key: str
#     ) -> str:
#         """Save small file and return URL - matches the expected signature"""
#         self.files[key] = file_content
#         return f'https://mock-bucket.com/{key}'


# async def setup_services():
#     """Set up all required services for testing"""
#     logger.info('Setting up services...')

#     # Setup database with tables
#     db_client = await setup_test_database()

#     # Create repositories
#     features_repository = SQLAlchemyRepository(ReferenceImageFeatures, db_client)
#     sift_features_repository = SIFTFeaturesRepository(SIFTFeatures, db_client)

#     # Create IKB repository
#     ikb_repository_db = SQLAlchemyRepository(ImageKnowledgeBase, db_client)
#     ikb_repository = IKBRepository(ikb_repository_db)

#     # Create services
#     algorithm_factory = AlgorithmFactory()
#     algorithm_service = AlgorithmService(algorithm_factory)
#     cloud_storage = MockCloudStorage()
#     reference_image_service = ReferenceImageService(
#         cloud_storage_manager=cloud_storage,
#         features_repository=features_repository,
#         sift_features_repository=sift_features_repository,
#         algorithm_service=algorithm_service,
#         bucket_name='test-bucket',
#     )
#     image_matching_service = ImageMatchingService(
#         algorithm_factory=algorithm_factory,
#         reference_service=reference_image_service,
#         active_algorithm_type=AlgorithmType.SIFT,
#         algorithm_config={'sift': {'max_features': 1000}},
#     )
#     ikb_service = IKBService(
#         image_matching_service=image_matching_service,
#         reference_image_service=reference_image_service,
#         ikb_repository=ikb_repository,
#     )

#     return ikb_service, db_client


# def image_to_base64_data_url(image_path: str) -> str:
#     """Convert image file to base64 data URL"""
#     with open(image_path, 'rb') as image_file:
#         image_data = image_file.read()
#         base64_data = base64.b64encode(image_data).decode('utf-8')
#         return f'data:image/png;base64,{base64_data}'


# @pytest.mark.skip(reason='Skipping')
# async def test_create_ikb_and_add_images():
#     """Test creating an IKB and adding multiple images to it"""
#     logger.info('🧪 Test: Create IKB and add Images')

#     ikb_service, db_client = await setup_services()

#     try:
#         # Step 1: Create IKB
#         logger.info(' Step 1: Creating IKB...')
#         create_request = CreateIKBRequest(
#             name='Gold Image Matching IKB',
#             description='Test IKB for gold image matching and analysis',
#             ikb_type=IKBType.GOLD_MATCHING,
#             algorithm_type=AlgorithmType.SIFT,
#             config={'threshold': 0.8, 'max_features': 1000},
#         )

#         ikb_info = await ikb_service.create_ikb(create_request)
#         logger.info(f'✅ IKB created: {ikb_info.ikb_id}')
#         logger.info(f'   Name: {ikb_info.name}')
#         logger.info(f'   Type: {ikb_info.ikb_type}')
#         logger.info(f'   Algorithm: {ikb_info.algorithm_type}')
#         logger.info(f'   Status: {ikb_info.status}')
#         logger.info(f'   Image Count: {ikb_info.image_count}')

#         # Step 2: add multiple images using real test images
#         logger.info('�� Step 2: adding images...')
#         test_images_dir = Path(__file__).parent / 'test_images'

#         # Use the actual test images
#         test_images = [
#             {'name': 'image1.png', 'description': 'Test image 1'},
#             {'name': 'image2.png', 'description': 'Test image 2'},
#             {'name': 'image3.png', 'description': 'Test image 3'},
#         ]

#         added_images = []
#         for i, img_info in enumerate(test_images, 1):
#             logger.info(f"   adding image {i}/3: {img_info['name']}")

#             # Get the full path to the test image
#             image_path = test_images_dir / img_info['name']

#             add_request = IKBImageAddRequest(
#                 ikb_id=ikb_info.ikb_id,
#                 image_data=image_to_base64_data_url(str(image_path)),
#                 reference_id=f'test_image_{i}',
#                 metadata={
#                     'description': img_info['description'],
#                     'image_file': img_info['name'],
#                 },
#             )

#             result = await ikb_service.add_image_to_ikb(add_request)
#             added_images.append(result)
#             logger.info(f"   ✅ added: {result['reference_id']}")  # Use correct key

#         # Step 3: Verify IKB properties
#         logger.info('🔍 Step 3: Verifying IKB properties...')
#         updated_ikb = await ikb_service.get_ikb(ikb_info.ikb_id)

#         assert updated_ikb is not None, 'IKB should exist'
#         assert (
#             updated_ikb.image_count == 3
#         ), f'Expected 3 images, got {updated_ikb.image_count}'
#         assert (
#             updated_ikb.status == IKBStatus.ACTIVE
#         ), f'Expected ACTIVE status, got {updated_ikb.status}'

#         logger.info('✅ IKB verification passed:')
#         logger.info(f'   - Image count: {updated_ikb.image_count}')
#         logger.info(f'   - Status: {updated_ikb.status}')
#         logger.info(f'   - Created at: {updated_ikb.created_at}')
#         logger.info(f'   - Updated at: {updated_ikb.updated_at}')

#         # Step 4: List all IKBs
#         logger.info('📋 Step 4: Listing all IKBs...')
#         all_ikbs = await ikb_service.list_ikbs()
#         logger.info(f'   Found {len(all_ikbs)} IKB(s)')
#         for ikb in all_ikbs:
#             logger.info(f'   - {ikb.name} ({ikb.ikb_id}): {ikb.image_count} images')

#         logger.info('🎉 Test completed successfully!')
#         return ikb_info.ikb_id, added_images

#     except Exception as e:
#         logger.error(f'❌ Test failed: {e}')
#         import traceback

#         traceback.print_exc()
#         raise
#     finally:
#         await db_client.close()


# @pytest.mark.skip(reason='Skipping')
# async def test_ikb_search_with_query_image():
#     """Test searching within an IKB using the query image"""
#     logger.info(' Test: IKB Search with Query Image')

#     ikb_service, db_client = await setup_services()

#     try:
#         # Step 1: Create IKB
#         logger.info(' Step 1: Creating IKB...')
#         create_request = CreateIKBRequest(
#             name='Photo Matching IKB',
#             description='Test IKB for photo matching and similarity search',
#             ikb_type=IKBType.PHOTO_MATCHING,
#             algorithm_type=AlgorithmType.SIFT,
#             config={'threshold': 0.7, 'max_features': 1000},
#         )

#         ikb_info = await ikb_service.create_ikb(create_request)
#         logger.info(f'✅ Created IKB: {ikb_info.name} (ID: {ikb_info.ikb_id})')

#         # Step 2: add reference images using real test images
#         logger.info('📤 Step 2: adding reference images...')
#         test_images_dir = Path(__file__).parent / 'test_images'

#         # add the reference images
#         reference_images = []
#         for i, image_name in enumerate(['image1.png', 'image2.png', 'image3.png'], 1):
#             image_path = test_images_dir / image_name

#             add_request = IKBImageAddRequest(
#                 ikb_id=ikb_info.ikb_id,
#                 image_data=image_to_base64_data_url(str(image_path)),
#                 reference_id=f'ref-photo-{i:03d}',
#                 metadata={'category': f'photo_{i}', 'add_order': i},
#             )

#             add_result = await ikb_service.add_image_to_ikb(add_request)
#             reference_images.append(add_result['reference_id'])  # Use correct key
#             logger.info(f"✅ added reference {i}: {add_result['reference_id']}")

#         # Verify all images added
#         updated_ikb = await ikb_service.get_ikb(ikb_info.ikb_id)
#         assert updated_ikb.image_count == 3
#         logger.info(f'✅ IKB has {updated_ikb.image_count} reference images')

#         # Step 3: Search with query image
#         logger.info('🔍 Step 3: Searching with query image...')
#         query_image_path = test_images_dir / 'query.png'

#         from image_search_module.models.ikb_models import IKBSearchRequest

#         search_request = IKBSearchRequest(
#             ikb_id=ikb_info.ikb_id,
#             image_data=image_to_base64_data_url(str(query_image_path)),
#             max_results=5,
#             threshold=0.6,
#         )

#         search_result = await ikb_service.search_in_ikb(search_request)
#         logger.info(f'✅ Search completed: {len(search_result.matches)} matches found')

#         # Verify search results
#         assert search_result.ikb_id == ikb_info.ikb_id
#         assert search_result.ikb_name == ikb_info.name
#         assert search_result.algorithm_used == 'sift'
#         assert search_result.total_images_searched == 3
#         assert len(search_result.matches) > 0

#         # Step 4: Analyze search results
#         logger.info(' Step 4: Analyzing search results...')
#         logger.info(f'   Query ID: {search_result.query_id}')
#         logger.info(f'   IKB: {search_result.ikb_name}')
#         logger.info(f'   Algorithm: {search_result.algorithm_used}')
#         logger.info(f'   Total images searched: {search_result.total_images_searched}')
#         logger.info(f'   Processing time: {search_result.processing_time_ms:.2f}ms')
#         logger.info(f'   Matches found: {len(search_result.matches)}')

#         # Log detailed match information
#         for i, match in enumerate(search_result.matches):
#             logger.info(f'   Match {i+1}:')
#             logger.info(f"     - Reference ID: {match['reference_id']}")
#             logger.info(f"     - Match Score: {match['match_score']:.4f}")
#             logger.info(f"     - Is Match: {match['is_match']}")
#             logger.info(f"     - Confidence: {match['confidence']:.4f}")
#             logger.info(f"     - Processing Time: {match['processing_time_ms']:.2f}ms")

#         logger.info(' Search test completed successfully!')
#         logger.info('📊 Summary:')
#         logger.info(f'   - IKB: {ikb_info.name}')
#         logger.info(f'   - Reference Images: {len(reference_images)}')
#         logger.info('   - Query Image: query.png')
#         logger.info(f'   - Matches Found: {len(search_result.matches)}')
#         logger.info(
#             f"   - Best Match Score: {max(match['match_score'] for match in search_result.matches):.4f}"
#         )

#         return ikb_info.ikb_id, search_result

#     except Exception as e:
#         logger.error(f'❌ Test failed: {e}')
#         import traceback

#         traceback.print_exc()
#         raise
#     finally:
#         await db_client.close()


# async def main():
#     """Main test function"""
#     try:
#         # Test 1: Create IKB and add images
#         # logger.info('🚀 Starting IKB Create and add Test')
#         # ikb_id, added_images = await test_create_ikb_and_add_images()
#         # logger.info(f'✅ Create/add test passed! IKB ID: {ikb_id}')
#         # logger.info(f'✅ added {len(added_images)} images')

#         # Test 2: Search with query image
#         logger.info('\n🚀 Starting IKB Search Test')
#         search_ikb_id, search_result = await test_ikb_search_with_query_image()
#         logger.info(f'✅ Search test passed! IKB ID: {search_ikb_id}')
#         logger.info(f'✅ Found {len(search_result.matches)} matches')

#     except Exception as e:
#         logger.error(f'❌ Test failed: {e}')
#         sys.exit(1)


# if __name__ == '__main__':
#     asyncio.run(main())
