from uuid import uuid4
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status, UploadFile
from starlette.datastructures import Headers
from io import BytesIO


async def create_session(test_session: AsyncSession, test_user_id, test_session_id):
    user = User(
        id=test_user_id,
        email='test@example.com',
        password='hashed_password',
        first_name='Test',
        last_name='User',
    )

    # Create a session in the database
    db_session = Session(
        id=test_session_id, user_id=test_user_id, device_info='test_device'
    )

    async with test_session() as session:
        session.add(user)
        session.add(db_session)
        await session.commit()


@pytest.mark.asyncio
async def test_upload_document_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    file_content = b'This is a test document content.'
    test_file = UploadFile(
        filename='test_document.txt',
        file=BytesIO(file_content),
        headers=Headers({'content-type': 'text/plain'}),
    )
    test_file.size = len(file_content)

    response = test_client.post(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={'file': (test_file.filename, test_file.file, test_file.content_type)},
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert (
        response_data['data']['message']
        == 'Created the knowledge base documents and embeddings successfully'
    )
    assert response_data['data']['knowledge_base_id'] == str(kb_id)


@pytest.mark.asyncio
async def test_upload_document_kb_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_kb_id = uuid4()
    file_content = b'This is a test document content.'
    test_file = UploadFile(
        filename='test_document.txt',
        file=BytesIO(file_content),
        headers=Headers({'content-type': 'text/plain'}),
    )
    test_file.size = len(file_content)

    response = test_client.post(
        f'/floware/v1/knowledge-bases/{non_existent_kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={'file': (test_file.filename, test_file.file, test_file.content_type)},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Knowledge Base with the given id does not exist'
    )


@pytest.mark.asyncio
async def test_upload_document_kb_id_not_exists(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    # Upload a document for the first time
    file_content = b'First document content.'
    test_file_1 = UploadFile(
        filename='document_1.txt',
        file=BytesIO(file_content),
        headers=Headers({'content-type': 'text/plain'}),
    )
    test_file_1.size = len(file_content)

    response_1 = test_client.post(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={
            'file': (test_file_1.filename, test_file_1.file, test_file_1.content_type)
        },
    )
    assert response_1.status_code == status.HTTP_200_OK
    file_content_2 = b'Second document content.'
    test_file_2 = UploadFile(
        filename='document_2.txt',
        file=BytesIO(file_content_2),
        headers=Headers({'content-type': 'text/plain'}),
    )
    test_file_2.size = len(file_content_2)
    kb_id = uuid4()
    response_2 = test_client.post(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={
            'file': (test_file_2.filename, test_file_2.file, test_file_2.content_type)
        },
    )

    assert response_2.status_code == status.HTTP_400_BAD_REQUEST
    response_data_2 = response_2.json()
    assert (
        response_data_2['meta']['error']
        == 'Knowledge Base with the given id does not exist'
    )


@pytest.mark.asyncio
async def test_get_documents_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB for Get',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    # Upload a document
    file_content = b'Content of doc 1.'
    test_file = UploadFile(
        filename='doc1.txt',
        file=BytesIO(file_content),
        headers=Headers({'content-type': 'text/plain'}),
    )
    test_file.size = len(file_content)
    response = test_client.post(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={'file': (test_file.filename, test_file.file, test_file.content_type)},
    )
    assert response.status_code == status.HTTP_200_OK

    # Upload another document
    file_content_2 = b'Content of doc 2.'
    test_file_2 = UploadFile(
        filename='doc2.pdf',
        file=BytesIO(file_content_2),
        headers=Headers({'content-type': 'application/pdf'}),
    )
    test_file_2.size = len(file_content_2)
    async with test_session() as session:
        new_kb_document_2 = KnowledgeBaseDocuments(
            knowledge_base_id=kb_id,
            file_path='gcs_url/doc2.pdf',
            file_name='doc2.pdf',
            file_type='pdf',
            file_size=len(file_content_2),
        )
        session.add(new_kb_document_2)
        await session.commit()

    # Retrieve documents
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert len(response_data['data']['resources']) == 2
    assert response_data['data']['resources'][0]['file_name'] == 'doc1.txt'
    assert response_data['data']['resources'][1]['file_name'] == 'doc2.pdf'


@pytest.mark.asyncio
async def test_get_documents_filter_by_type(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Filter',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    # Manually add documents of different types
    async with test_session() as session:
        doc1 = KnowledgeBaseDocuments(
            knowledge_base_id=kb_id,
            file_path='gcs_url/file1.txt',
            file_name='file1.txt',
            file_type='plain',
            file_size=100,
        )
        doc2 = KnowledgeBaseDocuments(
            knowledge_base_id=kb_id,
            file_path='gcs_url/file2.pdf',
            file_name='file2.pdf',
            file_type='pdf',
            file_size=200,
        )
        doc3 = KnowledgeBaseDocuments(
            knowledge_base_id=kb_id,
            file_path='gcs_url/file3.txt',
            file_name='file3.txt',
            file_type='plain',
            file_size=150,
        )
        session.add_all([doc1, doc2, doc3])
        await session.commit()

    # Retrieve documents filtered by type 'plain'
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{kb_id}/documents?file_type=plain',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert len(response_data['data']['resources']) == 2
    assert response_data['data']['resources'][0]['file_name'] == 'file1.txt'
    assert response_data['data']['resources'][1]['file_name'] == 'file3.txt'


@pytest.mark.asyncio
async def test_get_documents_no_documents_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base but no documents
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB No Docs',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    # Retrieve documents
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert len(response_data['data']['resources']) == 0


@pytest.mark.asyncio
async def test_delete_document_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB for Delete',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    # Manually add a document to be deleted
    doc_id = uuid4()
    async with test_session() as session:
        new_kb_document = KnowledgeBaseDocuments(
            id=doc_id,
            knowledge_base_id=kb_id,
            file_path='gcs_url/doc_to_delete.txt',
            file_name='doc_to_delete.txt',
            file_type='plain',
            file_size=100,
        )
        session.add(new_kb_document)
        await session.commit()

    # Delete the document
    delete_response = test_client.delete(
        f'/floware/v1/knowledge-bases/{kb_id}/documents/{doc_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    response_data = delete_response.json()
    assert (
        response_data['data']['message']
        == 'Deleted the Knowledge Base Documents and embeddings records successfully'
    )
    assert response_data['data']['knowledge_base_id'] == str(kb_id)

    # Verify deletion by trying to retrieve it
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert get_response.status_code == status.HTTP_200_OK
    assert len(get_response.json()['data']['resources']) == 0


@pytest.mark.asyncio
async def test_delete_document_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB for Delete Non Existent',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    non_existent_doc_id = uuid4()
    delete_response = test_client.delete(
        f'/floware/v1/knowledge-bases/{kb_id}/documents/{non_existent_doc_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert delete_response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = delete_response.json()
    assert (
        response_data['meta']['error'] == 'Document not found for this knowledge base'
    )
