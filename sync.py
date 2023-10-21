#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import requests

from optparse import OptionParser
from optparse import Option
from optparse import OptionValueError
from datetime import date
from datetime import datetime

from withings2 import WithingsAccount
from fit import FitEncoder_Weight

from garth.exc import GarthHTTPError
from garminconnect import (
  Garmin,
  GarminConnectAuthenticationError,
  GarminConnectConnectionError,
  GarminConnectTooManyRequestsError,
)

GARMIN_TOKENSTORE = "./config"
GARMIN_SECRET_FILE = "gsecret.json"
GARMIN_TOKEN_FILE = "gtoken.json"
GARMIN_USERNAME = ""
GARMIN_PASSWORD = ""

class DateOption(Option):
  def check_date(option, opt, value):
    valid_formats = ['%Y-%m-%d', '%Y%m%d', '%Y/%m/%d']
    for f in valid_formats:
      try:
        dt = datetime.strptime(value, f)
        return dt.date()
      except ValueError:
        pass
    raise OptionValueError('option %s: invalid date or format: %s. use following format: %s'
                 % (opt, value, ','.join(valid_formats)))

  TYPES = Option.TYPES + ('date',)
  TYPE_CHECKER = Option.TYPE_CHECKER.copy()
  TYPE_CHECKER['date'] = check_date


def main():
  global GARMIN_TOKENSTORE, GARMIN_SECRET_FILE, GARMIN_TOKEN_FILE, GARMIN_USERNAME, GARMIN_PASSWORD

  # Printing to stdout, not via logger yet
  print("%s - Sync Withings to Garmin" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
#  print("Python version %s.%s.%s" % sys.version_info[:3])

  # Check if secret config file exists, if so load garmin username and password
  if os.path.isfile(GARMIN_TOKENSTORE + GARMIN_SECRET_FILE):
    with open(GARMIN_TOKENSTORE + GARMIN_SECRET_FILE) as secret_file:
      secret = json.load(secret_file)
      GARMIN_USERNAME = secret["user"]
      GARMIN_PASSWORD = secret["password"]

  usage = 'usage: sync.py [options]'
  p = OptionParser(usage=usage, option_class=DateOption)
  p.add_option('-c', '--config', default='./config', type='string', metavar='dir', help="json configuration folder, default: ./config")

  p.add_option('--garmin-username', '--gu',  default=GARMIN_USERNAME, type='string', metavar='<user>', help='username to login Garmin Connect.')
  p.add_option('--garmin-password', '--gp', default=GARMIN_PASSWORD, type='string', metavar='<pass>', help='password to login Garmin Connect.')

  p.add_option('-f', '--fromdate', type='date', default="2022-01-01", metavar='<date>', help="Start date from the range, default: 2002-01-01")
  p.add_option('-t', '--todate', type='date', default=date.today(), metavar='<date>', help="End date from the range, default: Today")

  p.add_option('--no-upload', action='store_true', help="Don't upload to Garmin Connect. Output binary-strings to stdout.")

  p.add_option('-v', '--verbose', action='store_true', help='Run verbosely')
  (opts, args) = p.parse_args()

  # Set the locations of the config files
  if opts.config:
    GARMIN_TOKENSTORE = opts.config
    GARMIN_SECRET_FILE = opts.config + "/" + GARMIN_SECRET_FILE
    GARMIN_TOKEN_FILE  = opts.config + "/" + GARMIN_TOKEN_FILE

  # If no username set but config location given, set garmin username and password from config file
  if len(opts.garmin_username) == 0 and os.path.isfile(GARMIN_SECRET_FILE):
    if opts.verbose: print("Loading config file")
    with open(GARMIN_SECRET_FILE) as secret_file:
      secret = json.load(secret_file)
      opts.garmin_username = secret["user"]
      opts.garmin_password = secret["password"]

  if(opts.verbose):
    print("Configuration:", opts)

  # Sync Withings to Garmin
  sync(**opts.__dict__)


def init_garmin(garmin_username, garmin_password, verbose_print):
  """Initialize Garmin API with your credentials."""
  try:
    verbose_print(f"Trying to login to Garmin Connect using token data from '{GARMIN_TOKENSTORE}' ...\n")
    garmin = Garmin()
    garmin.login(GARMIN_TOKENSTORE)
  except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
    # Session is expired. You'll need to log in again
    verbose_print(
      "Login tokens not present, will login with your Garmin Connect credentials to generate them.\n"
      f"They will be stored in '{GARMIN_TOKENSTORE}' for future use.\n"
    )
    try:
      garmin = Garmin(garmin_username, garmin_password)
      garmin.login()
      # Save tokens for next login
      garmin.garth.dump(GARMIN_TOKENSTORE)

    except (
      FileNotFoundError,
      GarthHTTPError,
      GarminConnectAuthenticationError,
      requests.exceptions.HTTPError,
    ) as err:
      print(err)
      return None

  return garmin

def sync(config, garmin_username, garmin_password, fromdate, todate, no_upload, verbose):
  def verbose_print(s):
    if verbose:
      if no_upload:
        sys.stderr.write(s)
      else:
        sys.stdout.write(s)

  if len(garmin_username) == 0 or len(garmin_password) == 0:
    print("Garmin username or password not set!")
    return

  # Withings API
  withings = WithingsAccount(config_dir=config)

  startdate = int(time.mktime(fromdate.timetuple()))
  enddate = int(time.mktime(todate.timetuple())) + 86399

  groups = withings.getMeasurements(startdate=startdate, enddate=enddate)

  # create fit file
  verbose_print('generating fit file...\n')
  fit = FitEncoder_Weight()
  fit.write_file_info()
  fit.write_file_creator()

  for group in groups:
    # get extra physical measurements
    dt = group.get_datetime()
    weight = group.get_weight()
    fat_ratio = group.get_fat_ratio()
    muscle_mass = group.get_muscle_mass()
    hydration = group.get_hydration()
    bone_mass = group.get_bone_mass()

    fit.write_device_info(timestamp=dt)
    fit.write_weight_scale(
      timestamp=dt,
      weight=weight,
      percent_fat=fat_ratio,
      percent_hydration=(hydration * 100.0 / weight) if (hydration and weight) else None,
      bone_mass=bone_mass,
      muscle_mass=muscle_mass
    )
    verbose_print('appending weight scale record... %s %skg %s%%\n' % (dt, weight, fat_ratio))
  fit.finish()

  if no_upload:
    sys.stdout.buffer.write(fit.getvalue())
    return

  # DEBUG: test.fit contain data from Withings Healthmate
  # out_file = open('test.fit', 'wb')
  # out_file.write(fit.getvalue())

  verbose_print("Fit values: " + str(fit.getvalue()) + "\n")

  # garmin connect
  garmin = init_garmin(garmin_username, garmin_password, verbose_print)
  verbose_print("Attempting to upload fit file...\n")
  activityfilename = "/tmp/f.fit"
  with open(activityfilename,'wb') as activityfile:
    activityfile.write(fit.getvalue())

  try:
    r = garmin.upload_activity(activityfilename)
    r.raise_for_status()
    print("Withings fit values uploaded to Garmin Connect.")
  except Exception as ex:
    print("Failed to upload:", ex)

  if not verbose:
    # Remove fit file
    os.remove(activityfilename)

if __name__ == '__main__':
	main()
