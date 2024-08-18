import pickle
from openai import AzureOpenAI
from tools.data_generation.financial_data_generator import DatasetGenerator

def get_all_file_names(folder):
    from os import listdir
    from os.path import isfile, join
    file_paths = [folder  + "/" + f for f in listdir(folder) if isfile(join(folder, f))]
    return file_paths

pk_files = get_all_file_names("bin")
print(pk_files)


sample_file = "bin/Elective_Paper_BIL_P.pdf.pkl"
with open(sample_file, 'rb') as f:
    account_ratios = pickle.load(f)


client = AzureOpenAI(
    api_key="< api key>",  
    api_version="2024-02-15-preview",
    azure_endpoint="end point",
    azure_deployment="gpt-4"
)
generator = DatasetGenerator(client)

generator.generate_from_texts(
    texts=account_ratios,
    max_questions=len(account_ratios) * 10,
)
