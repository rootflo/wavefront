import os

ROOT_DIR = os.getcwd()


def read_yaml_as_string(file_path: str) -> str:
    config_path = os.path.join(ROOT_DIR, file_path.lstrip('/'))
    with open(config_path, 'r') as file:
        yaml_content = file.read()
    return yaml_content
