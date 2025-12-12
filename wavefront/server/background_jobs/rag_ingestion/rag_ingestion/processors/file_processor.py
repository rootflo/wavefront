import os
import tempfile
import textract
from typing import Union


class FileProcessor:
    def process_file(self, file_content: bytes, file_type: str) -> Union[str, bytes]:
        mime_type = file_type

        if mime_type.startswith('text/plain'):
            return file_content.decode('utf-8')

        if mime_type.startswith('image/'):
            return file_content

        if mime_type.startswith('application/'):
            try:
                sub_type = mime_type.split('/')[1]
            except IndexError:
                raise ValueError(
                    f'Unsupported file type: Malformed MIME type "{mime_type}"'
                )

            # Set delete=False to keep the file until we manually call os.unlink
            with tempfile.NamedTemporaryFile(
                mode='w+b', delete=False, suffix=f'.{sub_type}'
            ) as temp_file:
                temp_file.write(file_content)
                temp_file.flush()  # Ensure data is written to disk before processing
                temp_file_path = temp_file.name

            try:
                # Process the file using its path
                text_content = textract.process(
                    temp_file_path, method='pdfminer'
                ).decode('utf-8')
                return text_content

            except Exception as e:
                # Re-raise processing errors
                raise RuntimeError(f'Text extraction failed for {mime_type}: {e}')

            finally:
                os.unlink(temp_file_path)

        else:
            raise ValueError(f'Unsupported file type: {mime_type}')
