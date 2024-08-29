import random
import string

def random_str(length: int = 5):
    letters = string.ascii_letters + string.digits
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str

def randomize_name(name: str):
    return "{}-{}".format(name, random_str(5))

def agent_name_from_randomized_name(name: str):
    return name.split("-")[0]