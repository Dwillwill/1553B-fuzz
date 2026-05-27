CXX ?= g++

ADAPTER := libmil1553_board_adapter.so
VENDOR_DIR ?= ../Linux/SO

CXXFLAGS += -std=c++11 -Wall -Wextra -fPIC -I$(VENDOR_DIR)
LDFLAGS += -shared -L$(VENDOR_DIR)
LDLIBS += -lmil1553api

.PHONY: all clean smoke

all: $(ADAPTER)

$(ADAPTER): mil1553_board_adapter.cpp mil1553_board_adapter.h
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ mil1553_board_adapter.cpp $(LDLIBS)

smoke: smoke_bc_once

smoke_bc_once: smoke_bc_once.cpp mil1553_board_adapter.cpp mil1553_board_adapter.h
	$(CXX) $(CXXFLAGS) -o $@ smoke_bc_once.cpp mil1553_board_adapter.cpp -L$(VENDOR_DIR) $(LDLIBS)

clean:
	rm -f $(ADAPTER) smoke_bc_once
