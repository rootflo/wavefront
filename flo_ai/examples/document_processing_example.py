#!/usr/bin/env python3
"""
Document Processing Examples for Flo AI Framework

This example demonstrates the new document processing capabilities including:
- PDF and TXT document support
- Document analysis with agents
- Document processing tools
- YAML-based document workflows
"""

import asyncio
import os
import base64
from pathlib import Path
from flo_ai.models import DocumentMessageContent, TextMessageContent, UserMessage
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.arium import AriumBuilder
from flo_ai.llm import OpenAI, Gemini
from flo_ai.models.document import DocumentType

openai_api_key = os.getenv('OPENAI_API_KEY')
google_api_key = os.getenv('GOOGLE_API_KEY')


def create_sample_txt_file():
    """Create a sample TXT file for testing."""
    sample_text = """
# Sample Document for Testing

This is a sample text document created for testing the Flo AI document processing capabilities.

## Introduction

The Flo AI framework now supports processing of PDF and TXT documents with an extensible
architecture that can be easily expanded to support additional document formats in the future.

## Key Features

1. Document Processing: Extract text from PDF and TXT files
2. Agent Integration: Agents can now accept documents as inputs
3. Tool Support: Ready-to-use tools for document analysis
4. LLM Integration: Works with OpenAI, Gemini, and other supported LLMs

## Technical Implementation

The document processing system uses:
- DocumentMessage class for structured document inputs
- DocumentProcessor utility for extensible document handling
- LLM-specific formatting for optimal processing

## Conclusion

This document processing capability makes Flo AI more versatile for real-world applications
that need to analyze and process various document formats.
"""

    file_path = Path('sample_document.txt')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(sample_text)

    return str(file_path)


def create_sample_pdf_file():
    """Create a sample PDF file for testing."""
    file_path = Path('sample_document.pdf')

    # Create PDF with reportlab
    doc = SimpleDocTemplate(str(file_path), pagesize=letter)
    styles = getSampleStyleSheet()

    # Build the document content
    story = []

    # Title
    title = Paragraph('Sample PDF Document for Flo AI Testing', styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))

    # Introduction
    intro_text = """
    This is a sample PDF document created for testing the Flo AI document processing capabilities.
    The PDF format testing demonstrates the framework's ability to handle structured documents
    with formatting, multiple pages, and various content types.
    """
    intro = Paragraph(intro_text, styles['Normal'])
    story.append(intro)
    story.append(Spacer(1, 12))

    # Section 1
    section1_title = Paragraph('Document Processing Features', styles['Heading2'])
    story.append(section1_title)

    features_text = """
    1. PDF Text Extraction: Advanced parsing of PDF content including formatted text
    2. Bytes Processing: Handle PDF documents from memory without file system access
    3. Base64 Encoding: Process documents encoded in base64 format for API transmission
    4. Multi-format Support: Seamless handling of both PDF and TXT documents
    5. Agent Integration: Direct document input to AI agents for analysis
    """
    features = Paragraph(features_text, styles['Normal'])
    story.append(features)
    story.append(Spacer(1, 12))

    # Section 2
    section2_title = Paragraph('Technical Architecture', styles['Heading2'])
    story.append(section2_title)

    technical_text = """
    The Flo AI document processing system leverages:
    • DocumentMessage class for unified document representation
    • DocumentProcessor with extensible format handlers
    • LLM-specific document formatting for optimal AI processing
    • Async processing pipeline for efficient document handling
    """
    technical = Paragraph(technical_text, styles['Normal'])
    story.append(technical)
    story.append(Spacer(1, 12))

    # Conclusion
    conclusion_title = Paragraph('Use Cases', styles['Heading2'])
    story.append(conclusion_title)

    conclusion_text = """
    This comprehensive document processing capability enables Flo AI to handle real-world
    applications including:

    • Document analysis and summarization
    • Content extraction and search
    • Multi-document comparison and insights
    • Workflow automation with document inputs
    • API-based document processing services
    """
    conclusion = Paragraph(conclusion_text, styles['Normal'])
    story.append(conclusion)

    # Build the PDF
    doc.build(story)

    return str(file_path)


async def example_1_basic_document_agent():
    """Example 1: Basic document processing with an agent"""
    print('\n' + '=' * 60)
    print('EXAMPLE 1: Basic Document Processing with Agent')
    print('=' * 60)

    # Create sample file
    txt_file = create_sample_txt_file()

    try:
        # Read file and convert to base64
        with open(txt_file, 'rb') as f:
            txt_bytes = f.read()
            txt_base64 = base64.b64encode(txt_bytes).decode('utf-8')

        # Create document message
        document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.TXT.value, base64=txt_base64
            )
        )

        # Create document analysis agent
        llm = OpenAI(
            model='gpt-4o-mini', api_key=openai_api_key
        )  # Use OpenAI for this example

        agent = (
            AgentBuilder()
            .with_name('Document Analyzer')
            .with_prompt(
                'You are a document analysis expert. Analyze the provided document and provide insights about its content, structure, and key points.'
            )
            .with_llm(llm)
            .build()
        )

        # Process document with agent
        result = await agent.run([document])

        print('📄 Document Analysis Result:')
        print(result)

    except Exception as e:
        print(f'❌ Error in example 1: {e}')
        if 'Not implemented document processing' in str(e):
            print(
                "💡 Note: This LLM doesn't support document processing yet. Try with Gemini LLM."
            )

    finally:
        # Clean up
        if os.path.exists(txt_file):
            os.remove(txt_file)


async def example_2_document_workflow():
    """Example 3: Document processing workflow with YAML"""
    print('\n' + '=' * 60)
    print('EXAMPLE 2: Document Processing Workflow')
    print('=' * 60)

    # Create sample file
    txt_file = create_sample_txt_file()

    try:
        # Create document analysis workflow with proper router configuration
        workflow_yaml = """
        metadata:
          name: document-analysis-workflow
          version: 2.0.0
          description: "Document analysis workflow with intelligent routing"

        arium:
          agents:
            - name: intake_agent
              role: "Document Intake"
              job: "Initial document processing and content assessment."
              model:
                provider: openai
                name: gpt-4o-mini
              settings:
                temperature: 0.1

            - name: content_analyzer
              role: "Document Content Analyst"
              job: "Analyze document content for themes, insights, structure, and key information."
              model:
                provider: openai
                name: gpt-4o-mini
              settings:
                temperature: 0.3

            - name: summary_generator
              role: "Summary Writer"
              job: "Create comprehensive and informative summaries of analyzed content."
              model:
                provider: openai
                name: gpt-4o-mini
              settings:
                temperature: 0.2

          routers:
            - name: analysis_router
              type: smart
              routing_options:
                content_analyzer: "Route here for detailed content analysis of the document"
                summary_generator: "Route here if the content is already analyzed and ready for summarization"
              model:
                provider: openai
                name: gpt-4o-mini
              settings:
                temperature: 0.1
                context_description: "a document processing workflow that analyzes then summarizes content"

          workflow:
            start: intake_agent
            edges:
              - from: intake_agent
                to: [content_analyzer, summary_generator]
                router: analysis_router
              - from: content_analyzer
                to: [summary_generator]
            end: [summary_generator]
        """
        with open(txt_file, 'rb') as f:
            txt_bytes = f.read()
            txt_base64 = base64.b64encode(txt_bytes).decode('utf-8')
        # Create document message for workflow processing
        document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.TXT.value, base64=txt_base64
            )
        )

        # Build and run workflow with DocumentMessage
        print('🔄 Running document analysis workflow...')

        workflow = AriumBuilder().from_yaml(yaml_str=workflow_yaml).build()

        result = await workflow.run(
            [
                document,
                UserMessage(TextMessageContent(text='process this document')),
            ]
        )

        print('📊 Workflow Analysis Results:')
        for i, message in enumerate(result, 1):
            # Convert message to string if it's a DocumentMessage or other object
            message_str = str(message)
            print(
                f'{i}. {message_str[:200]}...'
                if len(message_str) > 200
                else f'{i}. {message_str}'
            )
            print()

    except Exception as e:
        print(f'❌ Error in example 2: {e}')
        if 'OPENAI_API_KEY' in str(e):
            print('💡 Make sure to set your OPENAI_API_KEY environment variable')

    finally:
        # Clean up
        if os.path.exists(txt_file):
            os.remove(txt_file)


async def example_6_gemini_document_processing():
    """Example 6: Document processing with Gemini LLM (if available)"""
    print('\n' + '=' * 60)
    print('EXAMPLE 6: Document Processing with Gemini LLM')
    print('=' * 60)

    # Create sample file
    txt_file = create_sample_txt_file()

    try:
        with open(txt_file, 'rb') as f:
            txt_bytes = f.read()
            txt_base64 = base64.b64encode(txt_bytes).decode('utf-8')
        # Create document message
        document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.TXT.value, base64=txt_base64
            )
        )

        # Create document analysis agent with Gemini
        llm = Gemini(model='gemini-2.5-flash', api_key=google_api_key)

        agent = (
            AgentBuilder()
            .with_name('Gemini Document Processor')
            .with_prompt(
                'You are an advanced document analysis AI. Provide detailed insights about the document structure, content themes, and actionable recommendations.'
            )
            .with_llm(llm)
            .build()
        )

        # Process document with Gemini
        result = await agent.run([document])

        print('🤖 Gemini Document Analysis:')
        print(result)

    except Exception as e:
        print(f'❌ Error in example 6: {e}')
        if 'api_key' in str(e).lower():
            print('💡 Make sure to set your Google API key for Gemini')

    finally:
        # Clean up
        if os.path.exists(txt_file):
            os.remove(txt_file)


async def example_3_pdf_document_processing():
    """Example 3: PDF document processing with agents"""
    print('\n' + '=' * 60)
    print('EXAMPLE 3: PDF Document Processing')
    print('=' * 60)

    # Create sample PDF file
    pdf_file = create_sample_pdf_file()

    try:
        with open(pdf_file, 'rb') as f:
            pdf_bytes = f.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        # Create document message for PDF
        document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.PDF.value, base64=pdf_base64
            )
        )

        # Create PDF analysis agent
        llm = OpenAI(model='gpt-4o-mini', api_key=openai_api_key)

        agent = (
            AgentBuilder()
            .with_name('PDF Document Analyzer')
            .with_prompt(
                'You are a PDF document analysis expert. Analyze the provided PDF document and provide insights about its content, structure, formatting, and key information.'
            )
            .with_llm(llm)
            .build()
        )

        # Process PDF document with agent
        result = await agent.run([document])

        print('📄 PDF Document Analysis Result:')
        print(result)

    except Exception as e:
        print(f'❌ Error in example 3: {e}')
        if 'Not implemented document processing' in str(e):
            print("💡 Note: This LLM doesn't support PDF document processing yet.")

    finally:
        # Clean up
        if os.path.exists(pdf_file):
            os.remove(pdf_file)


async def example_4_document_bytes_processing():
    """Example 4: Processing documents from bytes data"""
    print('\n' + '=' * 60)
    print('EXAMPLE 4: Document Processing from Bytes')
    print('=' * 60)

    # Create sample files and read as bytes
    txt_file = create_sample_txt_file()
    pdf_file = create_sample_pdf_file()

    try:
        print('🔧 Testing Document Processing from Bytes Data\n')

        # # Process TXT from bytes
        print('1. Processing TXT document from bytes:')
        with open(txt_file, 'rb') as f:
            txt_bytes = f.read()
            txt_base64 = base64.b64encode(txt_bytes).decode('utf-8')

        txt_document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.TXT.value, base64=txt_base64
            )
        )

        # # Create agent for bytes processing
        llm = OpenAI(model='gpt-4o-mini', api_key=openai_api_key)
        agent = (
            AgentBuilder()
            .with_name('Bytes Document Processor')
            .with_prompt(
                'Analyze this document that was provided as bytes data. Focus on the content and structure.'
            )
            .with_llm(llm)
            .build()
        )

        result = await agent.run([txt_document])
        # print(f'   TXT from bytes analysis: {result[:100]}...\n')

        # Process PDF from bytes
        print('2. Processing PDF document from bytes:')
        with open(pdf_file, 'rb') as f:
            pdf_bytes = f.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        pdf_document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.PDF.value, base64=pdf_base64
            )
        )

        result = await agent.run([pdf_document])
        print(f'   PDF from bytes analysis: {result[:100]}...\n')

        # Test tools with bytes (using extract tools)
        print('3. Using document tools with bytes data:')
        # Note: Tools expect file paths, so we'll show the concept
        print(f'   TXT bytes size: {len(txt_bytes)} bytes')
        print(f'   PDF bytes size: {len(pdf_bytes)} bytes')
        print('   ✅ Documents successfully processed from bytes data')

    except Exception as e:
        print(f'❌ Error in example 4: {e}')

    finally:
        # Clean up
        if os.path.exists(txt_file):
            os.remove(txt_file)
        if os.path.exists(pdf_file):
            os.remove(pdf_file)


async def example_5_document_base64_processing():
    """Example 5: Processing documents from base64 encoded data"""
    print('\n' + '=' * 60)
    print('EXAMPLE 5: Document Processing from Base64')
    print('=' * 60)

    # Create sample files and encode as base64
    txt_file = create_sample_txt_file()
    pdf_file = create_sample_pdf_file()

    try:
        print('🔧 Testing Document Processing from Base64 Data\n')

        # Process TXT from base64
        print('1. Processing TXT document from base64:')
        with open(txt_file, 'rb') as f:
            txt_bytes = f.read()
            txt_base64 = base64.b64encode(txt_bytes).decode('utf-8')

        txt_document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.TXT.value, base64=txt_base64
            )
        )

        # Create agent for base64 processing
        llm = OpenAI(model='gpt-4o-mini', api_key=openai_api_key)
        agent = (
            AgentBuilder()
            .with_name('Base64 Document Processor')
            .with_prompt(
                'Analyze this document that was provided as base64 encoded data. Provide insights about the content.'
            )
            .with_llm(llm)
            .build()
        )

        result = await agent.run([txt_document])
        print(f'   TXT from base64 analysis: {result[:100]}...\n')

        # Process PDF from base64
        print('2. Processing PDF document from base64:')
        with open(pdf_file, 'rb') as f:
            pdf_bytes = f.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        pdf_document = UserMessage(
            content=DocumentMessageContent(
                mime_type=DocumentType.PDF.value, base64=pdf_base64
            )
        )

        result = await agent.run([pdf_document])
        print(f'   PDF from base64 analysis: {result[:100]}...\n')

        # Show base64 data info
        print('3. Base64 encoding information:')
        print(f'   TXT base64 length: {len(txt_base64)} characters')
        print(f'   PDF base64 length: {len(pdf_base64)} characters')
        print(f'   TXT base64 sample: {txt_base64[:50]}...')
        print('   ✅ Documents successfully processed from base64 data')

    except Exception as e:
        print(f'❌ Error in example 5: {e}')

    finally:
        # Clean up
        if os.path.exists(txt_file):
            os.remove(txt_file)
        if os.path.exists(pdf_file):
            os.remove(pdf_file)


async def main():
    """Run all document processing examples"""
    print('🚀 Flo AI Document Processing Examples')
    print('Demonstrating PDF and TXT document processing capabilities\n')

    try:
        # Run examples
        await example_1_basic_document_agent()
        # await example_2_document_workflow()
        await example_3_pdf_document_processing()
        await example_4_document_bytes_processing()
        await example_5_document_base64_processing()
        await example_6_gemini_document_processing()

        print('\n' + '=' * 60)
        print('🎉 ALL DOCUMENT PROCESSING EXAMPLES COMPLETED!')
        print('=' * 60)
        print('\n📋 Examples demonstrated:')
        print('   • Basic document processing with agents')
        print('   • YAML-based document workflows')
        print('   • PDF document processing and analysis')
        print('   • Document processing from bytes data')
        print('   • Document processing from base64 encoded data')
        print('   • Multi-LLM document support (OpenAI, Gemini)')
        print('\n💡 Key features showcased:')
        print(
            '   • DocumentMessage for structured document inputs (file_path, bytes, base64)'
        )
        print('   • Extensible document processor architecture')
        print('   • PDF and TXT document format support')
        print('   • LLM-agnostic document formatting')
        print('   • Integration with existing Arium workflows')

    except Exception as e:
        print(f'❌ Error running examples: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    # Check API keys
    if not os.getenv('OPENAI_API_KEY'):
        print('⚠️  Warning: OPENAI_API_KEY environment variable not set!')
        print('   Set it with: export OPENAI_API_KEY=your_api_key_here')
        print('   Some examples may fail without API keys.\n')

    asyncio.run(main())
