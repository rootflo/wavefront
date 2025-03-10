import random
import string


def random_str(length: int = 5):
    letters = string.ascii_letters + string.digits
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str


def rotate_array(nums, k: int = 1):
    k = k % len(nums)
    return nums[k:] + nums[:k]
