from datetime import datetime
import logging

from nuvlaedge.common.nuvlaedge_config import parse_arguments_and_initialize_logging
from nuvlaedge.security.security import Security

logger: logging.Logger = logging.getLogger()


def main():
    parse_arguments_and_initialize_logging('security')
    logger.info('Starting vulnerabilities scan module')

    scanner: Security = Security()

    logger.info('Starting NuvlaEdge security scan')

    # if security.settings.external_db and security.nuvla_endpoint and \
    #         (datetime.utcnow() - security.previous_external_db_update).total_seconds() >\
    #         security.settings.external_db_update_period:
    logger.info('Checking for updates on the vulnerability DB')
    scanner.update_vulscan_db()

    logger.info('Running vulnerability scan')
    scanner.run_scan()


if __name__ == '__main__':
    main()