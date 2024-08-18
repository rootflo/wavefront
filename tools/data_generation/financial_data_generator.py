import json
import time
import copy
import ray
import pickle
from tqdm import tqdm
from openai import OpenAI
from tools.data_generation.data_gen_prompt import default_prompt
from tools.data_generation.data_set_gen_tool import generate_dataset
from typing import List
from pydantic.main import BaseModel

class DatasetItem(BaseModel):
    question: str
    answer: str
    context: str


class Dataset(BaseModel):
    items: List[DatasetItem]

from openai import AzureOpenAI

@ray.remote(num_cpus=0)
def chat_completion_request(model: str, messages, pidx, tools=None, tool_choice=None, max_retries=2):
    client = AzureOpenAI(
        api_key="<api key>",  
        api_version="2024-02-15-preview",
        azure_endpoint="endpoint",
        azure_deployment="gpt-4"
        )
    retry_count = 0
    while retry_count <= max_retries:
        try:
            response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                )
            return (pidx, response)  
        except Exception as e:
            print("Unable to generate ChatCompletion response")
            print(f"Exception: {e}")
            retry_count + 1
    return (pidx, "")

class DatasetGenerator:

    def __init__(self, client: OpenAI):
        self.client = client
        ray.init("auto")

    def generate_from_texts(
        self,
        texts: List[str],
        max_questions=10,
        **kwargs,
    ) -> Dataset:
        # Get optional system prompt from kwargs
        system_prompt = kwargs.get("system_prompt", default_prompt)

        # Determine how many questions to generate per text
        num_texts = len(texts)
        questions_per_text = max_questions // num_texts

        progress_bar = tqdm(total=max_questions, desc="Generating questions", colour='green')

        # Generate dataset items
        items: List[DatasetItem] = []
        from typing import List
        max_concurrent_queries = 25
        queue: List = copy.copy(texts)
        start_time = time.time()
        in_progress, responses = [], []

        while queue or in_progress:
            try:
                if len(in_progress) < max_concurrent_queries and queue:
                    item = queue.pop()
                    in_progress.append(
                    chat_completion_request.remote(
                            model="gpt-4-turbo",
                            tools=generate_dataset(),
                            pidx=1,
                            tool_choice={"type": "function", "function": {"name": "generate_dataset"}},
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"Generate {questions_per_text} questions for the following block of text: {item}"}
                            ],
                        )
                    )

                ready, in_progress = ray.wait(in_progress, timeout=0.5)
                #if verbose:
                print(
                    f"# queries un-processed: {len(queue)}, in-progress: {len(in_progress)}, ready: {len(ready)}"
                )
                if ready:
                    pdix, response = ray.get(ready)[0]
                    tool_call = response.choices[0].message.tool_calls[0]
                    if tool_call:
                        function_params = json.loads(tool_call.function.arguments)
                        dataset_items = function_params.get("dataset_items")
                        dataset_items = [DatasetItem(**item) for item in dataset_items]
                        items.extend(dataset_items)
                        progress_bar.update(len(dataset_items))
            except Exception as e:
                print(f"Exception: {e}")
                print(f"Done in {time.time() - start_time:.2f}sec.")
                queue.append(item)

        # Ensure the progress bar is closed
        progress_bar.close()

        dataset = Dataset(
            items=items[:max_questions],
        )

        print("Total len: {}".format(len(dataset.items)))

        with open("final_checkpoint_{}.pkl".format(time.time()), 'wb') as f:
            pickle.dump(dataset.items, f)

        return dataset
        