#!/usr/bin/env python
import subprocess
import sys
import yaml
import os
from utils.utils import check_login, read_base_config, cli_parser, load_yaml
import cmd.oc


def cluster_loader(base_config):
  cmd_line_options = cli_parser()
  testconfig = load_yaml(cmd_line_options.config_file)
  
  oc_client = cmd.oc.ocBase(cmd_line_options, base_config, testconfig)
  oc_client.check_oc_version()
  

if __name__ == '__main__':
  check_login()
  base_config = read_base_config()
  cluster_loader(base_config)
