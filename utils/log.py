import logging
import sys

formatter = logging.Formatter(fmt='%(asctime)s :: %(process)d :: %(levelname)-8s :: %(message)s', datefmt='%Y-%m-%d::%H:%M:%S')
screen_handler = logging.StreamHandler(stream=sys.stdout)
screen_handler.setFormatter(formatter)

global logger
logger = logging.getLogger("clusterloader")
logger.setLevel(logging.DEBUG)
logger.addHandler(screen_handler)
