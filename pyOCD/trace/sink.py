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

import logging
import collections

## @brief Abstract interface for a trace event sink.
class TraceEventSink(object):
    ## @brief Handle a single trace event.
    # @param self
    # @param event An instance of TraceEvent or one of its subclasses.
    def receive(self, event):
        raise NotImplementedError()

## @brief Abstract interface for a trace event filter.
class TraceEventFilter(TraceEventSink):
    def __init__(self, sink=None):
        self._sink = sink

    ## @brief Connect the downstream trace sink or filter.
    def connect(self, sink):
        self._sink = sink
    
    ## @brief Handle a single trace event.
    #
    # Passes the event through the filter() method. If one or more objects are returned, they
    # are then passed to the trace sink connected to this filter (which may be another filter).
    #
    # @param self
    # @param event An instance of TraceEvent or one of its subclasses.
    def receive(self, event):
        event = self.filter(event)
        if (event is not None) and (self._sink is not None):
            if isinstance(event, collections.Iterable):
                for e in event:
                    self._sink.receive(event)
            else:
                self._sink.receive(event)
    
    ## @brief Filter a single trace event.
    #
    # @param self
    # @param event An instance of TraceEvent or one of its subclasses.
    # @return Either None, a single TraceEvent, or a sequence of TraceEvents.
    def filter(self, event):
        raise NotImplementedError()

## @brief Trace event sink that replicates events to multiple sinks.
class TraceEventTee(TraceEventSink):
    def __init__(self):
        self._sinks = []

    ## @brief Connect one or more downstream trace sinks.
    #
    # @param self
    # @param sinks If this parameter is a single object, it will be added to the list of
    #   downstream trace event sinks. If it is an iterable (list, tuple, etc.), then it will
    #   completely replace the current list of trace event sinks.
    def connect(self, sinks):
        if isinstance(sinks, collections.Iterable):
            self._sinks = sinks
        elif sinks not in self._sinks:
            self._sinks.append(sinks)

    ## @brief Replicate a single trace event to all connected downstream trace event sinks.
    # @param self
    # @param event An instance of TraceEvent or one of its subclasses.
    def receive(self, event):
        for sink in self._sinks:
            sink.receive(event)

