import tiktoken
from flo_utils.utils.log import logger


def truncate_to_n_tokens(text: str, n: int, model: str = 'gpt-4'):
    """Truncate a string to at most `n` tokens using OpenAI's tokenizer."""
    enc = tiktoken.encoding_for_model(model)
    input_tkns = enc.encode(text)
    logger.info(f'Total input tokens: {len(input_tkns)}, truncating to {n}')
    tokens = input_tkns[:n]
    return enc.decode(tokens)
