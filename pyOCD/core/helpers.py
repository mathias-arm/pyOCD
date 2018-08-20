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

from __future__ import print_function
from .session import Session
from ..probe.aggregator import DebugProbeAggregator
from time import sleep
import colorama
import six

# Init colorama here since this is currently the only module that uses it.
colorama.init()

## @brief Helper class for streamlining the probe discovery and session creation process.
#
# This class provides several static methods that wrap the DebugProbeAggregator methods
# with a simple command-line user interface, or provide a single method that performs
# a common access pattern.
class ConnectHelper(object):

    ## @brief Return a list of Session objects for all connected debug probes.
    #
    # This method is useful for listing detailed information about connected probes, especially
    # those that have associated boards, as the Session object will have a Board instance.
    #
    # The returned Session objects are not yet active, in that open() has not yet been called.
    @staticmethod
    def get_sessions_for_all_connected_probes(blocking=True, unique_id=None, options=None, **kwargs):
        probes = ConnectHelper.get_all_connected_probes(blocking=blocking, unique_id=unique_id)
        sessions = [Session(probe, options=options, **kwargs) for probe in probes]
        return sessions

    ## @brief Return a list of DebugProbe objects for all connected debug probes.
    @staticmethod
    def get_all_connected_probes(blocking=True, unique_id=None):
        printedMessage = False
        while True:
            allProbes = DebugProbeAggregator.get_all_connected_probes(unique_id=unique_id)
            sortedProbes = sorted(allProbes, key=lambda probe:probe.description + probe.unique_id)

            if not blocking:
                break
            elif len(sortedProbes):
                break
            else:
                if not printedMessage:
                    print(colorama.Fore.YELLOW + "Waiting for a debug probe to be connected..." + colorama.Style.RESET_ALL)
                    printedMessage = True
                sleep(0.01)
            assert len(sortedProbes) == 0

        return sortedProbes

    ## @brief List the connected debug probes.        
    @staticmethod
    def list_connected_probes():
        allProbes = ConnectHelper.get_all_connected_probes(blocking=False)
        if len(allProbes):
            ConnectHelper._print_probe_list(allProbes)
        else:
            print(colorama.Fore.RED + "No available debug probes are connected" + colorama.Style.RESET_ALL)

    ## @brief Create a session with a probe possibly chosen by the user.
    #
    # @return Either None or a Session instance.
    @staticmethod
    def session_with_chosen_probe(blocking=True, return_first=False,
                    unique_id=None, board_id=None, # board_id param is deprecated
                    init_board=True, options=None, **kwargs):
        # Get all matching probes, sorted by name.
        board_id = unique_id or board_id
        allProbes = ConnectHelper.get_all_connected_probes(blocking=blocking, unique_id=board_id)

        # Print some help if the user specified a unique ID, but more than one probe matches.
        if board_id is not None:
            if len(allProbes) > 1:
                print(colorama.Fore.RED + "More than one debug probe matches unique ID '%s':" % board_id + colorama.Style.RESET_ALL)
                board_id = board_id.lower()
                for probe in allProbes:
                    head, sep, tail = probe.unique_id.lower().rpartition(board_id)
                    highlightedId = head + colorama.Fore.RED + sep + colorama.Style.RESET_ALL + tail
                    print("%s | %s" % (
                        probe.description,
                        highlightedId))
                return None

        # Return if no boards are connected.
        if allProbes is None or len(allProbes) == 0:
            if board_id is None:
                print("No connected debug probes")
            else:
                print("A debug probe matching unique ID '%s' is not connected, or no connected probe matches" % board_id)
            return None # No boards to close so it is safe to return

        # Select first board
        if return_first:
            allProbes = allProbes[0:1]

        # Ask user to select boards if there is more than 1 left
        if len(allProbes) > 1:
            ConnectHelper._print_probe_list(allProbes)
            print(colorama.Fore.RED + " q => Quit")
            while True:
                print(colorama.Style.RESET_ALL)
                print("Enter the number of the debug probe to connect:")
                line = six.moves.input("> ")
                valid = False
                if line.strip().lower() == 'q':
                    return None
                try:
                    ch = int(line)
                    valid = 0 <= ch < len(allProbes)
                except ValueError:
                    pass
                if not valid:
                    print(colorama.Fore.YELLOW + "Invalid choice: %s\n" % line)
                    Session._print_probe_list(allProbes)
                    print(colorama.Fore.RED + " q => Exit" + colorama.Style.RESET_ALL)
                else:
                    break
            allProbes = allProbes[ch:ch + 1]

        assert len(allProbes) == 1
        session = Session(allProbes[0], options=options, **kwargs)
        if init_board:
            try:
                session.open()
            except:
                session.close()
                raise
        return session

    @staticmethod
    def _print_probe_list(probes):
        print(colorama.Fore.BLUE + "## => Board Name | Unique ID")
        print("-- -- ----------------------")
        for index, probe in enumerate(probes):
            print(colorama.Fore.GREEN + "%2d => %s | " % (index, probe.description) +
                colorama.Fore.CYAN + probe.unique_id + colorama.Style.RESET_ALL)
        print(colorama.Style.RESET_ALL, end='')
