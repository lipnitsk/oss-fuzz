# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Module for uploading artifacts using HTTP. Based on upload-http-client.ts."""
import json
import logging
import os
import time
import urllib
import urllib.error
import urllib.parse
import urllib.request

import requests

from github_actions_toolkit.artifact import config_variables
from github_actions_toolkit.artifact import utils
from github_actions_toolkit import http_client


def upload_file(parameters):
  """Based on uploadFileAsync. Note that this doesn't take
  index because we don't need it to do HTTP requests like the typescript code
  does."""
  # !!!
  # Skip gzip as it is unneeded for now.
  total_file_size = os.path.getsize(parameters['file'].absolute_file_path)
  if not upload_chunk(parameters['resourceUrl'],
                      parameters['file'].absolute_file_path,
                      total_file_size):
    return {
        'isSuccess': False,
        'successfulUploadSize': 0,
        'totalSize': total_file_size
    }
  return {
      'isSuccess': True,
      'successfulUploadSize': total_file_size,
      'totalSize': total_file_size
  }


def upload_chunk(resource_url, file_path, total_file_size):
  """Based on uploadChunk. Differences from upstream are because:
  1. HTTP client index since we don't need it to do HTTP uploads like typescript
  code.
  2. GZIP.
  """
  start = 0
  end = total_file_size - 1
  content_range = utils.get_content_range(start, end, total_file_size)
  upload_headers = utils.get_upload_headers('application/octet-stream',
                                            is_keep_alive=False,
                                            is_gzip=False,
                                            content_length=total_file_size,
                                            content_range=content_range)
  for _ in range(utils.MAX_API_ATTEMPTS):
    try:
      with open(file_path, 'rb') as file_handle:
        response = requests.put(
            resource_url, data=file_handle, headers=upload_headers)
        logging.debug('upload_chunk response: %s', response.text)
      return True
    except Exception as err:
      import pdb
      pdb.set_trace()
      pass

    time.sleep(utils.SLEEP_TIME)

  return False


def patch_artifact_size(size, artifact_name):
  """upload-http-client.js"""
  resource_url = utils.get_artifact_url()
  resource_url = _add_url_params(resource_url, {'artifactName': artifact_name})
  logging.debug('resource_url is %s.', resource_url)
  parameters = {'Size': size}
  data = json.dumps(parameters)
  headers = utils.get_upload_headers('application/json')
  for _ in range(utils.MAX_API_ATTEMPTS):
    # !!! Create better method for handling.
    try:
      do_post_request(resource_url, data, headers)
      break
    except urllib.error.HTTPError as http_error:
      code = http_error.getcode()
      if code == http_client.HTTPCode.BAD_REQUEST:
        logging.error('Artifact "%s" not found.', artifact_name)
        raise
      logging.error('Other error: %s', http_error)

    except ConnectionResetError:
      pass

    logging.debug('!!! failed to patch.')
    time.sleep(utils.SLEEP_TIME)
  logging.debug('Artifact "%s" successfully uploaded. Size: %d bytes',
                artifact_name, size)


def create_artifact_in_file_container(artifact_name, options):
  """upload-http-client.js"""
  parameters = {
      'Type': 'actions_storage',
      'Name': artifact_name,
  }

  # Set retention period.
  if options and 'retentionDays' in options:
    max_retention_str = config_variables.get_retention_days()
    parameters['RetentionDays'] = utils.get_proper_retention(
        options['retentionDays'], max_retention_str)

  data = json.dumps(parameters)
  artifact_url = utils.get_artifact_url()
  headers = utils.get_upload_headers('application/json')
  for _ in range(utils.MAX_API_ATTEMPTS):
    try:
      response = do_post_request(artifact_url, data, headers)
      r = response.read()
      print('create_artifact_in_file_container response:', r)
      return json.loads(r)
    except urllib.error.HTTPError as http_error:
      code = http_error.getcode()
      if code == http_client.HTTPCode.BAD_REQUEST:
        logging.error('Invalid artifact name: "%s". Request URL: %s.',
                      artifact_name, artifact_url)
        raise
      if code == http_client.HTTPCode.FORBIDDEN:
        logging.error('Unable to upload artifacts. Storage quota reached.')
        raise
      # Otherwise we can retry.

    except ConnectionResetError:
      pass

    time.sleep(utils.SLEEP_TIME)

  raise Exception('Can\'t retry creating artifact in file container again')


def do_post_request(url, data, headers=None):
  """Do a POST request to |url|."""
  if headers is None:
    headers = {}
  post_request = urllib.request.Request(url, data.encode(), headers)
  # !!! test error handling.
  return urllib.request.urlopen(post_request)


def upload_artifact_to_file_container(upload_url, files_to_upload, options):
  """upload-http-client.js."""
  logging.debug('File concurrency: %d, and chunk size: %d.',
                config_variables.UPLOAD_FILE_CONCURRENCY,
                config_variables.UPLOAD_CHUNK_SIZE)
  # By default, file uploads will continue if there is an error unless specified
  # differently in the options.
  if options:
    continue_on_error = options.get('continue_on_error', True)
  else:
    continue_on_error = True

  # Prepare the necessary parameters to upload all the files.
  upload_file_size = 0
  total_file_size = 0
  failed_items_to_report = []
  for file_to_upload in files_to_upload:
    url_params = {'itemPath': file_to_upload.upload_file_path}
    resource_url = _add_url_params(upload_url, url_params)
    upload_parameters = {
        'file': file_to_upload,
        'resourceUrl': resource_url,
        'maxChunkSize': config_variables.UPLOAD_CHUNK_SIZE,
        'continueOnError': continue_on_error
    }
    upload_file_result = upload_file(upload_parameters)
    upload_file_size += upload_file_result['successfulUploadSize']
    total_file_size += upload_file_result['totalSize']
    if not upload_file_result['isSuccess']:
      failed_items_to_report.append(file_to_upload)
      if not continue_on_error:
        logging.error('Stopping artifact upload due to error.')
        # !!! What do I do here?

  logging.info('Total size of files uploaded is %s bytes.', upload_file_size)
  return {
      'uploadSize': upload_file_size,
      'totalSize': total_file_size,
      'failedItems': failed_items_to_report
  }


def _add_url_params(url, params):
  """Returns |url| with the specified query |params| added."""
  # Parse URL into mutable format.
  # It's OK we use _asdict(), this is actually a public method.
  url_parts = urllib.parse.urlparse(url)._asdict()

  # Update URL.
  query = dict(urllib.parse.parse_qsl(url_parts['query']))
  query.update(params)
  url_parts['query'] = urllib.parse.urlencode(query)

  # Return a URL string.
  return urllib.parse.urlunparse(urllib.parse.ParseResult(**url_parts))
