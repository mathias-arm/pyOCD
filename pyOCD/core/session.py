# pyOCD debugger
# Copyright (c) 2018 Arm Limited
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ..board.board import Board
import logging
import six

DEFAULT_CLOCK_FREQ = 1000000 # 1 MHz

log = logging.getLogger('session')

## @brief Top-level object for a debug session.
#
# This class represents a debug session with a single debug probe. It is the root of the object
# graph, where it owns the debug probe and the board objects.
#
# Another important function of this class is that it contains a dictionary of session-scope
# user options. These would normally be passed in from the command line, or perhaps a config file.
#
# There are several static methods on Session that are designed to make it easy to create new
# sessions, with or without user interaction in the case of multiple available debug probes.
class Session(object):

    def __init__(self, probe, options=None, **kwargs):
        self._probe = probe
        self._closed = True
        self._inited = False
        
        # Update options.
        self._options = options or {}
        self._options.update(kwargs)
        
        # Create the board instance. Ask the probe if it has an associated board, and if
        # not then we create a generic one.
        self._board = probe.create_associated_board(self) \
                        or Board(self, self._options.get('target_override', None))
    
    @property
    def is_open(self):
        return self._inited and not self._closed
    
    @property
    def probe(self):
        return self._probe
    
    @property
    def board(self):
        return self._board
    
    @property
    def options(self):
        return self._options

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()
        return False

    ## @brief Initialize the session
    def open(self):
        if not self._inited:
            self._probe.open()
            self._probe.set_clock(self._options.get('frequency', DEFAULT_CLOCK_FREQ))
            self._board.init()
            self._inited = True
            self._closed = False

    ## @brief Close the session.
    def close(self):
        if self._closed:
            return
        self._closed = True

        log.debug("uninit session %s", self)
        if self._inited:
            try:
                self.board.uninit()
                self._inited = False
            except:
                log.error("exception during board uninit:", exc_info=True)
        
        if self._probe.is_open:
            try:
                self._probe.disconnect()
            except:
                log.error("probe exception during disconnect:", exc_info=True)
            try:
                self._probe.close()
            except:
                log.error("probe exception during close:", exc_info=True)

