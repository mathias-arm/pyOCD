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

## @brief JLink commands.
#
# From document RM08001-R7 J-Link USB Protocol
class Commands(object):
    EMU_CMD_VERSION                       = 0x01 # Retrieves the firmware version.
    EMU_CMD_RESET_TRST                    = 0x02
    EMU_CMD_RESET_TARGET                  = 0x03
    EMU_CMD_SET_SPEED                     = 0x05
    EMU_CMD_GET_STATE                     = 0x07
    EMU_CMD_SET_KS_POWER                  = 0x08
    EMU_CMD_REGISTER                      = 0x09
    EMU_CMD_GET_HW_INFO                   = 0xc1
    EMU_CMD_SELECT_IF                     = 0xc7
    EMU_CMD_HW_JTAG3                      = 0xcf
    EMU_CMD_GET_MAX_MEM_BLOCK             = 0xd4  # Retrieves the maximum memory block-size.
    EMU_CMD_HW_JTAG_WRITE                 = 0xd5
    EMU_CMD_HW_JTAG_GET_RESULT            = 0xd6
    EMU_CMD_HW_RESET0                     = 0xdc
    EMU_CMD_HW_RESET1                     = 0xdd
    EMU_CMD_GET_CAPS                      = 0xe8 # Retrieves capabilities of the emulator.
    EMU_CMD_GET_CPU_CAPS                  = 0xe9
    EMU_CMD_GET_CAPS_EX                   = 0xed # Retrieves capabilities (including extended ones) of the emulator.
    EMU_CMD_GET_HW_VERSION                = 0xf0 # Retrieves the hardware version of the emulator.
    EMU_CMD_READ_CONFIG                   = 0xf2
    EMU_CMD_WRITE_CONFIG                  = 0xf3
    EMU_CMD_WRITE_MEM                     = 0xf4
    EMU_CMD_READ_MEM                      = 0xf5
    EMU_REG_CMD_REGISTER                  = 0x64
    EMU_REG_CMD_UNREGISTER                = 0x65
    
    REG_HEADER_SIZE = 8
    REG_MIN_SIZE = 76

## @brief JLink capability bits
#
# These constants are bit numbers in the bitfields returned by the EMU_CMD_GET_CAPS and
# EMU_CMD_GET_CAPS_EX commands.
class Capabilities(object):
    EMU_CAP_RESERVED_1            = 0
    EMU_CAP_GET_HW_VERSION        = 1
    EMU_CAP_WRITE_DCC             = 2
    EMU_CAP_ADAPTIVE_CLOCKING     = 3
    EMU_CAP_READ_CONFIG           = 4
    EMU_CAP_WRITE_CONFIG          = 5
    EMU_CAP_TRACE                 = 6
    EMU_CAP_WRITE_MEM             = 7
    EMU_CAP_READ_MEM              = 8
    EMU_CAP_SPEED_INFO            = 9
    EMU_CAP_EXEC_CODE             = 10
    EMU_CAP_GET_MAX_BLOCK_SIZE    = 11
    EMU_CAP_GET_HW_INFO           = 12
    EMU_CAP_SET_KS_POWER          = 13
    EMU_CAP_RESET_STOP_TIMED      = 14
    EMU_CAP_RESERVED_2            = 15
    EMU_CAP_MEASURE_RTCK_REACT    = 16
    EMU_CAP_SELECT_IF             = 17
    EMU_CAP_RW_MEM_ARM79          = 18
    EMU_CAP_GET_COUNTERS          = 19
    EMU_CAP_READ_DCC              = 20
    EMU_CAP_GET_CPU_CAPS          = 21
    EMU_CAP_EXEC_CPU_CMD          = 22
    EMU_CAP_SWO                   = 23
    EMU_CAP_WRITE_DCC_EX          = 24
    EMU_CAP_UPDATE_FIRMWARE_EX    = 25
    EMU_CAP_FILE_IO               = 26
    EMU_CAP_REGISTER              = 27
    EMU_CAP_INDICATORS            = 28
    EMU_CAP_TEST_NET_SPEED        = 29
    EMU_CAP_RAWTRACE              = 30
    EMU_CAP_GET_EXT_CAPS          = 31

    NAMES = {
        EMU_CAP_RESERVED_1         : "Always 1.",
        EMU_CAP_GET_HW_VERSION     : "EMU_CMD_GET_HARDWARE_VERSION",
        EMU_CAP_WRITE_DCC          : "EMU_CMD_WRITE_DCC",
        EMU_CAP_ADAPTIVE_CLOCKING  : "adaptive clocking",
        EMU_CAP_READ_CONFIG        : "EMU_CMD_READ_CONFIG",
        EMU_CAP_WRITE_CONFIG       : "EMU_CMD_WRITE_CONFIG",
        EMU_CAP_TRACE              : "trace commands",
        EMU_CAP_WRITE_MEM          : "EMU_CMD_WRITE_MEM",
        EMU_CAP_READ_MEM           : "EMU_CMD_READ_MEM",
        EMU_CAP_SPEED_INFO         : "EMU_CMD_GET_SPEED",
        EMU_CAP_EXEC_CODE          : "EMU_CMD_CODE_...",
        EMU_CAP_GET_MAX_BLOCK_SIZE : "EMU_CMD_GET_MAX_BLOCK_SIZE",
        EMU_CAP_GET_HW_INFO        : "EMU_CMD_GET_HW_INFO",
        EMU_CAP_SET_KS_POWER       : "EMU_CMD_SET_KS_POWER",
        EMU_CAP_RESET_STOP_TIMED   : "EMU_CMD_HW_RELEASE_RESET_STOP_TIMED",
        EMU_CAP_RESERVED_2         : "Reserved",
        EMU_CAP_MEASURE_RTCK_REACT : "EMU_CMD_MEASURE_RTCK_REACT",
        EMU_CAP_SELECT_IF          : "EMU_CMD_HW_SELECT_IF",
        EMU_CAP_RW_MEM_ARM79       : "EMU_CMD_READ/WRITE_MEM_ARM79",
        EMU_CAP_GET_COUNTERS       : "EMU_CMD_GET_COUNTERS",
        EMU_CAP_READ_DCC           : "EMU_CMD_READ_DCC",
        EMU_CAP_GET_CPU_CAPS       : "EMU_CMD_GET_CPU_CAPS",
        EMU_CAP_EXEC_CPU_CMD       : "EMU_CMD_EXEC_CPU_CMD",
        EMU_CAP_SWO                : "EMU_CMD_SWO",
        EMU_CAP_WRITE_DCC_EX       : "EMU_CMD_WRITE_DCC_EX",
        EMU_CAP_UPDATE_FIRMWARE_EX : "EMU_CMD_UPDATE_FIRMWARE_EX",
        EMU_CAP_FILE_IO            : "EMU_CMD_FILE_IO",
        EMU_CAP_REGISTER           : "EMU_CMD_REGISTER",
        EMU_CAP_INDICATORS         : "EMU_CMD_INDICATORS",
        EMU_CAP_TEST_NET_SPEED     : "EMU_CMD_TEST_NET_SPEED",
        EMU_CAP_RAWTRACE           : "EMU_CMD_RAWTRACE",
        EMU_CAP_GET_EXT_CAPS       : "EMU_CAP_GET_EXT_CAPS",
    }

