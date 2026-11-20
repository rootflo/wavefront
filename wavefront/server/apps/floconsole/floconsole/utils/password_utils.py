import bcrypt

from common_module.blocking_io import run_in_pool


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), hashed_password.encode('utf-8')
    )


# bcrypt is deliberately slow (about 250 ms of CPU per call). From async code,
# use these: they run it on the 'cpu' pool so the event loop stays free.
# bcrypt releases the GIL, so threads do run it in parallel.


async def hash_password_async(password: str) -> str:
    return await run_in_pool('cpu', hash_password, password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await run_in_pool('cpu', verify_password, plain_password, hashed_password)
