"""RequestAwareLogger reports the caller's location, not its own."""

import logging

from common_module.log.logger import logger


def test_error_reports_the_call_site(caplog):
    with caplog.at_level(logging.ERROR, logger=logger.name):
        logger.error('x')

    assert caplog.records[-1].filename == 'test_logger.py'


def test_error_without_active_exception_does_not_raise(caplog):
    with caplog.at_level(logging.ERROR, logger=logger.name):
        logger.error('no exception here')

    assert caplog.records[-1].getMessage() == 'no exception here'


def test_exception_reports_the_call_site(caplog):
    with caplog.at_level(logging.ERROR, logger=logger.name):
        try:
            raise ValueError('bad')
        except ValueError:
            logger.exception('x')

    record = caplog.records[-1]
    assert record.filename == 'test_logger.py'
    assert record.exc_info is not None and record.exc_info[0] is ValueError
