"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2017 ARM Limited

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""
from __future__ import print_function

import os, sys
from time import sleep, time
from random import randrange
import traceback
import argparse

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

import pyOCD
from pyOCD.board import MbedBoard
from pyOCD.core.target import Target
from test_util import Test, TestResult
import logging

class ConnectTestResult(TestResult):
    def __init__(self):
        super(ConnectTestResult, self).__init__(None, None, None)

class ConnectTest(Test):
    def __init__(self):
        super(ConnectTest, self).__init__("Connect Test", connect_test)

    def run(self, board):
        passed = False
        try:
            result = self.test_function(board)
        except Exception as e:
            print("Exception %s when testing board %s" % (e, board.getUniqueID()))
            result = ConnectTestResult()
            result.passed = False
            traceback.print_exc(file=sys.stdout)
        result.board = board
        result.test = self
        return result


def connect_test(board):
    target_type = board.getTargetType()
    board_id = board.getUniqueID()
    binary_file = os.path.join(parentdir, 'binaries', board.getTestBinary())
    print("binary file: %s" % binary_file)

    test_pass_count = 0
    test_count = 0
    result = ConnectTestResult()

    # Install binary.
    live_board = MbedBoard.chooseBoard(board_id=board_id, frequency=1000000)
    memory_map = board.target.getMemoryMap()
    rom_region = memory_map.getBootMemory()
    rom_start = rom_region.start

    def test_connect(halt_on_connect, expected_state, resume):
        print("Connecting with halt_on_connect=%s" % halt_on_connect)
        live_board = MbedBoard.chooseBoard(board_id=board_id, frequency=1000000, init_board=False)
        live_board.target.setHaltOnConnect(halt_on_connect)
        live_board.init()
        print("Verifying target is", ("running" if (expected_state == Target.TARGET_RUNNING) else "halted"))
        if live_board.target.getState() == expected_state:
            passed = 1
            print("TEST PASSED")
        else:
            passed = 0
            print("TEST FAILED")
        print("Disconnecting with resume=%s" % resume)
        live_board.uninit(resume)
        live_board = None
        return passed

    # TEST CASE COMBINATIONS
    #
    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 1     run     False               run         False       run
    # 2     run     True                halt        False       halt
    # 3     halt    True                halt        True        run
    # 4     run     True                halt        True        run
    # 5     run     False               run         True        run
    # 6 <insert halt here>
    # 7     halt    False               halt        False       halt
    # 8     halt    True                halt        False       halt
    # 9     halt    False               halt        True        run
    # 10 <verify runnning here>

    print("\r\n\r\n----- FLASH NEW BINARY -----")
    live_board.flash.flashBinary(binary_file, rom_start)
    live_board.target.reset()
    test_count += 1
    print("Verifying target is running")
    if live_board.target.isRunning():
        test_pass_count += 1
        print("TEST PASSED")
    else:
        print("TEST FAILED")
    print("Disconnecting with resume=True")
    live_board.uninit(resume=True)
    live_board = None
    # Leave running.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 1     run     False               run         False       run
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=False, expected_state=Target.TARGET_RUNNING, resume=False)
    # Leave board running.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 2     run     True                halt        False       halt
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=True, expected_state=Target.TARGET_HALTED, resume=False)
    # Leave board halted.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 3     halt    True                halt        True        run
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=True, expected_state=Target.TARGET_HALTED, resume=True)
    # Leave board running.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 4     run     True                halt        True        run
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=True, expected_state=Target.TARGET_HALTED, resume=True)
    # Leave board running.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 5     run     False               run         True        run
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=False, expected_state=Target.TARGET_RUNNING, resume=True)
    # Leave board running.

    # 6 <insert halt here>
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=True, expected_state=Target.TARGET_HALTED, resume=False)
    # Leave board halted.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 7     halt    False               halt        False       halt
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=False, expected_state=Target.TARGET_HALTED, resume=False)
    # Leave board halted.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 8     halt    True                halt        False       halt
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=True, expected_state=Target.TARGET_HALTED, resume=False)
    # Leave board halted.

    # <#>   <enter> <halt_on_connect>   <expected>  <resume>    <exit>
    # 9     halt    False               halt        True        run
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=False, expected_state=Target.TARGET_HALTED, resume=True)
    # Leave board running.

    # 10 <verify runnning here>
    test_count += 1
    test_pass_count += test_connect(halt_on_connect=False, expected_state=Target.TARGET_RUNNING, resume=False)
    # Leave board running.

    print("\r\n\r\nTest Summary:")
    print("Pass count %i of %i tests" % (test_pass_count, test_count))
    if test_pass_count == test_count:
        print("CONNECT TEST SCRIPT PASSED")
    else:
        print("CONNECT TEST SCRIPT FAILED")

    result.passed = (test_count == test_pass_count)
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='pyOCD connect test')
    parser.add_argument('-d', '--debug', action="store_true", help='Enable debug logging')
    args = parser.parse_args()
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=level)
    board = pyOCD.board.mbed_board.MbedBoard.getAllConnectedBoards(close=True)[0]
    test = ConnectTest()
    result = [test.run(board)]
    test.print_perf_info(result)
