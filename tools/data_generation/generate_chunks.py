from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from tqdm import tqdm
import pickle

base_path = "dataset"
sample_file_path = base_path  + "/Elective_Paper_BIL_P.pdf"

def load_chunck_and_get_lines(file_path: str):
    text_splitter = RecursiveCharacterTextSplitter(
        # Set a really small chunk size, just to show.
        chunk_size=2000,
        chunk_overlap=500,
        length_function=len,
        is_separator_regex=False,
    )
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
        docs = loader.load()
    else:
        loader = TextLoader(file_path)
        docs = loader.load()
    texts = text_splitter.split_documents(docs)
    return list(map(lambda x: x.page_content, texts))

def get_all_file_names(folder):
    from os import listdir
    from os.path import isfile, join
    file_paths = [folder  + "/" + f for f in listdir(folder) if isfile(join(folder, f))]
    return file_paths

def create_text_data():
    files = get_all_file_names(base_path)
    progress_bar = tqdm(total=len(files), desc="Generating texts", colour='green')
    for file_name in files:
        print(file_name)
        progress_bar.update(1)
        lines = load_chunck_and_get_lines(file_name)
        with open('{}.pkl'.format(file_name), 'wb') as f:
            pickle.dump(lines, f)

create_text_data()