import logging
import os

def init_logger():
    if not os.path.exists("logs"):
        os.makedirs("logs")

    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s %(message)s',
                        datefmt='%d %b %Y %H:%M:%S',
                        handlers=[
                            logging.FileHandler("logs/main.log"),
                            logging.StreamHandler()
                        ])
    logger.info('Logging level %s', logging.root.level)
