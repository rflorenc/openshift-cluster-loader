#!/usr/bin/env python

from argparse import ArgumentParser
import subprocess, time, sys, os, yaml
from datetime import datetime
from multiprocessing import Process
from log import *
import ConfigParser


def cli_parser():
  cliparser = ArgumentParser()
  cliparser.add_argument("-f", "--file", dest="config_file",
                      help="This is the input config file used to define the test.",
                      metavar="FILE", default="pyconfig.yaml")
  cliparser.add_argument("-c", "--config-file", dest="base_config",
                      help="This is the input config file used to define the test.",
                      metavar="FILE", default="pyconfig.yaml")
  cliparser.add_argument("-n", "--namespace", dest="projectname",
                      help="Project under which to run the test",
                      default="testproj00")
  cliparser.add_argument("-d", "--clean",
                      action="store_true", dest="cleanall", default=True,
                      help="Clean the openshift environment created by the test.")
  cliparser.add_argument("--kubeconfig", dest="kubeconfig",
                      default=os.path.expanduser("~") + "/.kube/config",
                      help="Location of the default kubeconfig to use")
  cliparser.add_argument("-v", "--debug",
                      action="store_true", dest="debug", default=False,
                      help="Prints more detailed info to help debug an issue.")
  return cliparser.parse_args()

def check_login():
  try:
    ret = subprocess.check_call(["oc", "whoami"])
  except subprocess.CalledProcessError as ex:
    sys.exit("Not logged in via oc client. Exit.")

def read_base_config(config_file=".config.cfg"):
    if config_file is None:
        sys.exit(".config.cfg not found. Exit.")
    config = ConfigParser.SafeConfigParser()
    config.read(config_file)
    return config

def load_yaml(config_file):
  testconfig = {}
  with open(config_file) as stream:
    testconfig = yaml.load(stream, Loader=yaml.FullLoader)
    return testconfig

def calc_time(timestr):
    tlist = timestr.split()
    if tlist[1] == "s":
        return int(tlist[0])
    elif tlist[1] == "min":
        return int(tlist[0]) * 60
    elif tlist[1] == "ms":
        return int(tlist[0]) / 1000
    elif tlist[1] == "hr":
        return int(tlist[0]) * 3600
    else:
        logger.error("Invalid delay in rate_limit Exitting ........")
        sys.exit()
