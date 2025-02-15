"""
Generate Training Data Script

This script processes log files and tool descriptions to generate training datasets.
It handles both tool-based and chain-based data, transforming them into a proper format.

Usage:
    python generate_training_data.py --logger-path PATH --tool-path PATH [--output PATH]

Arguments:
    --logger-path: Path to the logger file containing tool and chain entries
    --tool-path: Path to the tool descriptions file
    --output: path to save the output
"""

import json
import argparse


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate training data from logs and tool descriptions'
    )
    parser.add_argument(
        '--logger-path',
        required=True,
        help='Path to the logger file containing tool and chain entries',
    )
    parser.add_argument(
        '--tool-path', required=True, help='Path to the tool descriptions file'
    )
    parser.add_argument('--output-path', required=True, help='path to save the output')
    return parser.parse_args()


def read_file(file_path):
    """
    Read and parse JSON lines from a file.
    Returns:
        List of parsed JSON objects
    """
    try:
        datas = []
        with open(file_path, 'r') as file:
            for line in file:
                datas.append(json.loads(line))
        return datas
    except FileNotFoundError:
        raise FileNotFoundError(f'Could not find file: {file_path}')
    except Exception as e:
        raise Exception(e)


def extracting_tool_details(tools, toolbox):
    dataset = []
    for tool in tools:
        query = tool.get('query')
        tool_name = tool.get('tool_name')
        for tool_d in toolbox[tool_name]:
            if tool_d.get('tool_name') == tool_name:
                description = tool_d['description']
                args = tool_d['args']
        tool_input = tool['input']
        dataset.append(
            {
                'query': query,
                'tool_name': tool_name,
                'description': description,
                'args': args,
                'tool_input': tool_input,
            }
        )
    return dataset


def tool_transformation(input_data):
    transform_data = {}

    for idx, data in enumerate(input_data):
        tool_name = data['tool_name']
        description = (data['description'],)
        args = data['args']
        tool_input = json.loads(data['tool_input'].replace("'", '"'))
        for _, value in args.items():
            if 'title' in value:
                del value['title']
        transformed_query = {
            'id': idx,
            'answers': json.dumps([{'name': tool_name, 'arguments': tool_input}]),
            'tools': json.dumps(
                [{'name': tool_name, 'description': description, 'parameters': args}]
            ),
        }
        transform_data[tool_name] = transformed_query
    return transform_data


def chain_transformation(chains, start_idx):
    chain_dataset = []

    for i, chain in enumerate(chains, start_idx):
        if chain.get('inputs'):
            chain_dataset.append(
                {
                    'query': chain['prompt'][0],
                    'id': i,
                    'answer': chain['outputs']['output'],
                }
            )
    return chain_dataset


def llm_transformation(llm_logs, tool_set):
    dataset = []
    for i, llm_log in enumerate(llm_logs):
        if llm_log['inputs'] and 'messages' in llm_log['inputs']:
            tools = None
            answer = llm_log['outputs']
            print()
            if (
                'type' in llm_log['outputs'][0]
                and llm_log['outputs'][0]['type'] == 'AgentAction'
            ):
                tools = tool_set[llm_log['outputs'][0]['tool']]
                answer = tools['answers']
            dataset.append(
                {
                    'query': llm_log['inputs']['messages'],
                    'id': i,
                    'answers': answer,
                    'tools': tools['tools'] if tools is not None else None,
                }
            )
    return dataset


if __name__ == '__main__':
    args = parse_arguments()

    logger_data = read_file(args.logger_path)
    tool_descriptions = read_file(args.tool_path)

    toolbox = {}
    for td in tool_descriptions:
        toolbox[td[0]['tool_name']] = td

    tools = [entry for entry in logger_data if entry['type'] == 'tool']
    llms = [entry for entry in logger_data if entry['type'] == 'llm']

    tool_extraction = extracting_tool_details(tools, toolbox)
    tool_transformed = tool_transformation(tool_extraction)
    training_data = llm_transformation(llms, tool_transformed)

    with open(args.output_path, 'w') as f:
        for data in training_data:
            f.write(json.dumps(data) + '\n')
