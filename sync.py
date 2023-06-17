#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from withings2 import WithingsAccount
from garmin import GarminConnect
from fit import FitEncoder_Weight

from optparse import OptionParser
from optparse import Option
from optparse import OptionValueError
from datetime import date
from datetime import datetime
import json
import time
import sys
import os


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
    # Check if default config file exists, if so load garmin username and password
    if os.path.isfile("config/secret.json"):
        with open('config/secret.json') as secret_file:                                                                                                                                                                              
            secret = json.load(secret_file)                                                                                                                                                                                          
            GARMIN_USERNAME = secret["user"]                                                                                                                                                                                         
            GARMIN_PASSWORD = secret["password"]                                                                                                                                                                                     
    else:
        GARMIN_USERNAME = ""
        GARMIN_PASSWORD = ""
                                                                                                                                                                                                                                 
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
                                                                                                                                                                                                                                 
    # If no username set but config location given, set garmin username and password from config file
    if len(opts.garmin_username) == 0 and os.path.isfile(opts.config + "/secret.json"):                                                                                                                                                                                                    
        if opts.verbose: print("Loading config file")
        with open(opts.config + "/secret.json") as secret_file:                                                                                                                                                                              
            secret = json.load(secret_file)                                                                                                                                                                                          
            opts.garmin_username = secret["user"]                                                                                                                                                                                         
            opts.garmin_password = secret["password"]     

    if(opts.verbose):
        print("Configuration:", opts)

    sync(**opts.__dict__)


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

	# verbose_print("Fit file: " + fit.getvalue())

	# garmin connect
	garmin = GarminConnect()
	session = garmin.login(garmin_username, garmin_password)
	verbose_print('attempting to upload fit file...\n')
	r = garmin.upload_file(fit.getvalue(), session)
	if r:
		print("Fit file uploaded to Garmin Connect")


if __name__ == '__main__':
	main()
