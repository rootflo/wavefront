import pickle


def get_all_file_names(folder):
    from os import listdir
    from os.path import isfile, join
    file_paths = [folder  + "/" + f for f in listdir(folder) if isfile(join(folder, f))]
    return file_paths

pk_files = get_all_file_names("bin/data-bank")

extended_list = []
for fl in pk_files:
    with open(fl, 'rb') as f:
        data = pickle.load(f)
    extended_list.extend(list(map(lambda x: { "question": x.question, "answer": x.answer, "context": x.context }, data)))


print(len(extended_list))

from pandas import DataFrame

df = (DataFrame(extended_list))

import pandas as pd
from datasets import Dataset
# Load data into a Pandas DataFrame
# df = pd.read_csv('data.csv')
# Convert the DataFrame into a Dataset
df.to_csv("ind-finance.csv")

