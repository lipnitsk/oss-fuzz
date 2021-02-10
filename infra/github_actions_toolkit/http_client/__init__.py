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
"""Module for HTTP code.
Based on https://github.com/actions/http-client/blob/main/index.ts"""

import enum


class HTTPCode(enum.Enum):
  """Enum representing meaning of HTTP codes."""
  BAD_REQUEST = 400
  FORBIDDEN = 403
  NOT_FOUND = 404
