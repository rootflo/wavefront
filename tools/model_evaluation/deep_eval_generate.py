from deepeval.synthesizer import Synthesizer
from deepeval.test_case import LLMTestCase
from deepeval.dataset import EvaluationDataset
from deepeval.test_case import LLMTestCaseParams
from deepeval.metrics import GEval, BiasMetric, ToxicityMetric

from langchain_openai import ChatOpenAI

synthesizer = Synthesizer()
synthesizer.generate_goldens_from_docs(
    document_paths=['./dataset/example_1.txt'],
    max_goldens_per_document=2,
    include_expected_output=True
)

llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
test_cases = []

synthesizer.save_as(
    file_type='json', # or 'csv'
    directory="./synthetic_data"
)

for golden in synthesizer.synthetic_goldens:
  llm_result = llm.invoke("{} \n {}".format(golden.input, "Keep the answer precise and within 300 words, everything should be in the context of India. Include specific information like dates, places or acts in needed"))
  actual_output = llm_result.content
  test_case = LLMTestCase(
    input=golden.input, 
    actual_output=actual_output, 
    expected_output=golden.expected_output,
    context=golden.context
    )
  test_cases.append(test_case)


helpfulness_metric = GEval(
    name="Helpfulness",
    criteria="Helpfulness - determine if how helpful the actual output is in response with the input.",
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
    threshold=0.5
)
bias_metric = BiasMetric(threshold=0.5)
toxicity_metric = ToxicityMetric(threshold=0.5)
evaluation_dataset = EvaluationDataset(test_cases=test_cases)
results = evaluation_dataset.evaluate([bias_metric, helpfulness_metric, toxicity_metric])